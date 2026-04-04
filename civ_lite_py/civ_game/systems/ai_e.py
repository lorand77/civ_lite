"""
AI E — controls player 0 (Rome) and player 1 (Greece).
Threat-Aware Scored AI: each CPU civ calls ai_take_turn(game, civ) once per turn.
All decisions are scored numerically; the AI picks the best score.
"""
from civ_game.entities.unit import get_reachable_tiles, get_attackable_tiles
from civ_game.map.hex_grid import hex_distance, hex_neighbors, hexes_in_range
from civ_game.systems.yields import compute_city_yields
from civ_game.systems.production import get_item_cost
from civ_game.data.units import UNIT_DEFS, UNIT_UPGRADES
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.data.techs import TECH_DEFS

# ---------------------------------------------------------------------------
# Leader flavor weights — same code, different playstyles
# ---------------------------------------------------------------------------
LEADER_FLAVORS = {
    0: {  # Rome — balanced expansionist
        "military":   1.1,
        "expansion":  0.8,
        "science":    0.9,
        "buildings":  1.0,
        "aggression": 1.0,
    },
    1: {  # Greece — science-leaning, attacks late with better units
        "military":   0.7,
        "expansion":  0.9,
        "science":    1.3,
        "buildings":  1.3,
        "aggression": 0.7,
    },
    2: {  # Huns — aggressive early rusher
        "military":   1.8,
        "expansion":  1.2,
        "science":    0.5,
        "buildings":  0.6,
        "aggression": 1.8,
    },
    3: {  # Babylon — builder, attacks with bought army
        "military":   0.8,
        "expansion":  0.8,
        "science":    1.8,
        "buildings":  1.7,
        "aggression": 0.9,
    },
}


# ---------------------------------------------------------------------------
# Grand Strategy Layer
# ---------------------------------------------------------------------------
_civ_strategies: dict = {}   # {player_index: {"strategy": str, "turn": int}}
STRATEGY_REEVAL_INTERVAL = 25

STRATEGY_BOOSTS = {
    "DOMINATION": {
        "military":   1.4,
        "aggression": 1.3,
        "expansion":  0.8,
        "science":    0.7,
        "buildings":  0.7,
    },
    "SCIENCE": {
        "military":   0.8,
        "aggression": 0.7,
        "expansion":  0.9,
        "science":    1.5,
        "buildings":  1.3,
    },
    "EXPANSION": {
        "military":   0.9,
        "aggression": 0.8,
        "expansion":  1.6,
        "science":    0.9,
        "buildings":  1.0,
    },
}


def _pick_strategy(game, civ, base_flavors) -> str:
    my_units = [u for u in civ.units if not u.is_civilian]
    my_strength = sum(UNIT_DEFS[u.unit_type]["strength"] for u in my_units)

    # DOMINATION score
    dom = base_flavors["military"] * 12 + base_flavors["aggression"] * 10
    dom += my_strength * 0.4
    dom -= len(civ.techs_researched) * 1
    for other in game.civs:
        if other.player_index == civ.player_index or other.is_eliminated:
            continue
        for city in other.cities:
            if my_units:
                dist = min(hex_distance(u.q, u.r, city.q, city.r) for u in my_units)
                if dist < 8:
                    dom += 15
                    break

    # SCIENCE score
    sci = base_flavors["science"] * 12 + base_flavors["buildings"] * 6
    sci += len(civ.techs_researched) * 2
    sci += len(civ.cities) * 3
    sci -= my_strength * 0.2

    # EXPANSION score
    exp = base_flavors["expansion"] * 12
    total_land = sum(1 for t in game.tiles.values() if t.terrain != "ocean")
    owned = sum(1 for t in game.tiles.values() if t.owner == civ.player_index)
    exp += (1.0 - owned / max(1, total_land)) * 20
    exp -= len(civ.cities) * 4
    if game.turn > 120:
        exp -= 20

    return max(
        [("DOMINATION", dom), ("SCIENCE", sci), ("EXPANSION", exp)],
        key=lambda x: x[1],
    )[0]


def _get_effective_flavors(game, civ) -> dict:
    """Return flavor weights boosted by the civ's current grand strategy."""
    base = LEADER_FLAVORS[civ.player_index]
    state = _civ_strategies.get(civ.player_index)

    if state is None or game.turn - state["turn"] >= STRATEGY_REEVAL_INTERVAL:
        strategy = _pick_strategy(game, civ, base)
        _civ_strategies[civ.player_index] = {"strategy": strategy, "turn": game.turn}
    else:
        strategy = state["strategy"]

    # Emergency override: city under direct threat → always DOMINATION
    under_attack = any(
        hex_distance(u.q, u.r, city.q, city.r) <= 4
        for other in game.civs
        if other.player_index != civ.player_index and not other.is_eliminated
        for u in other.units if not u.is_civilian
        for city in civ.cities
    )
    if under_attack:
        strategy = "DOMINATION"

    boosts = STRATEGY_BOOSTS[strategy]
    return {k: base[k] * boosts[k] for k in base}


# ---------------------------------------------------------------------------
# Component 1 — Danger Map
# ---------------------------------------------------------------------------
def _build_danger_map(game, civ) -> dict:
    """
    Returns {(q, r): danger_value} — sum of enemy unit strengths that could
    reach or attack each tile. Melee units threaten tiles within move range;
    ranged units additionally threaten tiles within their attack range using
    ranged_strength.
    """
    danger = {}
    for other in game.civs:
        if other.player_index == civ.player_index or other.is_eliminated:
            continue
        for unit in other.units:
            if unit.is_civilian:
                continue
            defn = UNIT_DEFS[unit.unit_type]
            strength = defn["strength"]
            move_range = defn["moves"]
            attack_range = defn.get("range", 0)
            ranged_strength = defn.get("ranged_strength", 0)
            for (q, r) in game.tiles:
                d = hex_distance(unit.q, unit.r, q, r)
                if d <= move_range:
                    danger[(q, r)] = danger.get((q, r), 0) + strength
                elif attack_range and d <= attack_range:
                    danger[(q, r)] = danger.get((q, r), 0) + ranged_strength
    return danger


# ---------------------------------------------------------------------------
# Component 2 — City Threat Assessment
# ---------------------------------------------------------------------------
def _city_threat(city, danger) -> int:
    """Sum of danger values within radius 3 of city."""
    total = 0
    for (q, r), val in danger.items():
        if hex_distance(city.q, city.r, q, r) <= 3:
            total += val
    return total


# ---------------------------------------------------------------------------
# Component 3 — Attack Target Selection
# ---------------------------------------------------------------------------
def _select_attack_target(game, civ, flavors):
    """Pick the single best enemy city to focus on. Returns None if too weak."""

    my_strength = sum(
        UNIT_DEFS[u.unit_type]["strength"]
        for u in civ.units if not u.is_civilian
    )

    best_score = -9999
    best_city = None

    for other in game.civs:
        if other.player_index == civ.player_index or other.is_eliminated:
            continue

        enemy_strength = sum(
            UNIT_DEFS[u.unit_type]["strength"]
            for u in other.units if not u.is_civilian
        )

        # Veto: never attack if enemy is too strong relative to aggression flavor
        max_enemy_ratio = 1.0 + flavors["aggression"] * 0.5
        if my_strength == 0 or enemy_strength > my_strength * max_enemy_ratio:
            continue

        for city in other.cities:
            score = 0

            score += (my_strength - enemy_strength) * 2
            score += (50 - city.hp) * 1.5

            if city == other.original_capital:
                score += 40

            if civ.cities:
                min_dist = min(
                    hex_distance(city.q, city.r, mc.q, mc.r)
                    for mc in civ.cities
                )
                score -= min_dist * 1.5
            else:
                score -= 30

            if score > best_score:
                best_score = score
                best_city = city

    return best_city


# ---------------------------------------------------------------------------
# Component 4 — Unit Role Assignment
# ---------------------------------------------------------------------------
def _assign_roles(civ, danger, attack_target) -> tuple:
    """
    Returns (roles, defender_cities):
      roles:           {id(unit): role_str}   — "DEFENDER", "ATTACKER", or "PATROL"
      defender_cities:  {id(unit): city}       — which city a DEFENDER is assigned to
    """
    roles = {}
    defender_cities = {}

    threatened_cities = [
        c for c in civ.cities
        if _city_threat(c, danger) > 15
    ]

    military_units = [u for u in civ.units if not u.is_civilian]

    def nearest_threat_dist(unit):
        if not threatened_cities:
            return 999
        return min(hex_distance(unit.q, unit.r, c.q, c.r) for c in threatened_cities)

    military_units.sort(key=nearest_threat_dist)

    assigned_defender_cities = set()
    for unit in military_units:
        if not threatened_cities:
            break
        nearest = min(
            threatened_cities,
            key=lambda c: hex_distance(unit.q, unit.r, c.q, c.r)
        )
        dist = hex_distance(unit.q, unit.r, nearest.q, nearest.r)
        if dist <= 6 and id(nearest) not in assigned_defender_cities:
            roles[id(unit)] = "DEFENDER"
            defender_cities[id(unit)] = nearest
            assigned_defender_cities.add(id(nearest))

    for unit in military_units:
        if id(unit) not in roles:
            roles[id(unit)] = "ATTACKER" if attack_target else "PATROL"

    return roles, defender_cities


# ---------------------------------------------------------------------------
# Component 4b — BFS Distance Map (terrain-only, ignores unit obstacles)
# ---------------------------------------------------------------------------
def _bfs_dist_map(q, r, tiles):
    """Returns {(q,r): steps} — BFS distance from (q,r) to every reachable tile."""
    from collections import deque
    from civ_game.map.terrain import TERRAIN_PASSABLE
    dist = {(q, r): 0}
    queue = deque([(q, r, 0)])
    while queue:
        cq, cr, d = queue.popleft()
        for nq, nr in hex_neighbors(cq, cr):
            if (nq, nr) in dist:
                continue
            tile = tiles.get((nq, nr))
            if not tile or not TERRAIN_PASSABLE[tile.terrain]:
                continue
            dist[(nq, nr)] = d + 1
            queue.append((nq, nr, d + 1))
    return dist


# ---------------------------------------------------------------------------
# Component 5 — Military Unit Action
# ---------------------------------------------------------------------------
def _act_military_unit(game, civ, unit, roles, defender_cities, attack_target, danger, flavors, assault_ready=True):
    if unit.moves_left == 0:
        return

    role = roles.get(id(unit), "PATROL")
    defn = UNIT_DEFS[unit.unit_type]

    xp_factor = 1.0 + unit.xp * 0.01          # mirrors combat.py xp_bonus
    my_eff_str = defn["strength"] * xp_factor  # effective strength incl. XP

    best_score = -9999
    best_action = None  # ("attack", q, r) | ("move", q, r, cost) | ("fortify",)

    attackable = get_attackable_tiles(unit, game.tiles)
    reachable = get_reachable_tiles(unit, game.tiles, game.turn)

    # 1. Score attack options
    for (tq, tr) in attackable:
        tile = game.tiles.get((tq, tr))
        if not tile:
            continue

        target_city = tile.city
        target_unit = tile.unit or tile.civilian

        score = 0

        if target_city and target_city.owner != civ.player_index:
            # Hold the assault on the target city until enough strength is mustered
            if role == "ATTACKER" and target_city == attack_target and not assault_ready:
                continue
            hp_ratio = unit.hp / defn["hp_max"]
            if unit.hp < 30:
                continue  # never attack a city at critical HP
            score += 30
            score += (50 - target_city.hp) * 0.5
            if target_city == attack_target:
                score += 25
            score -= (1.0 - hp_ratio) * 60
        elif target_unit and target_unit.owner != civ.player_index:
            # No city — attack the unit directly
            t_defn = UNIT_DEFS[target_unit.unit_type]
            t_str = t_defn["strength"]
            hp_ratio = unit.hp / defn["hp_max"]

            score += (my_eff_str - t_str) * 4
            score += (100 - target_unit.hp) * 0.3
            score -= (1.0 - hp_ratio) * 30
        else:
            continue  # nothing valid to attack here

        # Role modifiers
        if role == "DEFENDER":
            score *= 0.4
        elif role == "ATTACKER" and target_city == attack_target:
            score *= 1.5

        score *= flavors["military"]

        if score > best_score:
            best_score = score
            best_action = ("attack", tq, tr)

    # 2. Score movement options
    attack_path_dist = None
    if role == "ATTACKER" and attack_target:
        attack_path_dist = _bfs_dist_map(attack_target.q, attack_target.r, game.tiles)

    current_danger = danger.get((unit.q, unit.r), 0)
    should_retreat = current_danger > 0 and not attackable

    for (tq, tr), cost in reachable.items():
        score = 0

        if role == "DEFENDER":
            assigned_city = defender_cities.get(id(unit))
            if assigned_city:
                current_dist = hex_distance(unit.q, unit.r, assigned_city.q, assigned_city.r)
                new_dist = hex_distance(tq, tr, assigned_city.q, assigned_city.r)
                score = (current_dist - new_dist) * 15
                tile = game.tiles.get((tq, tr))
                if tile and tile.city == assigned_city:
                    score += 20

        elif role == "ATTACKER" and attack_target:
            current_dist = attack_path_dist.get((unit.q, unit.r), 999)
            new_dist = attack_path_dist.get((tq, tr), 999)

            if not assault_ready:
                HOLD_DIST = 5
                if new_dist < HOLD_DIST:
                    continue  # don't advance inside the staging perimeter
            score = (current_dist - new_dist) * 12

            tile_danger = danger.get((tq, tr), 0)
            if tile_danger > my_eff_str * 1.5:
                score -= 40

        else:  # PATROL
            nearest_enemy_dist = 999
            for other in game.civs:
                if other.player_index == civ.player_index or other.is_eliminated:
                    continue
                for eu in other.units:
                    d = hex_distance(tq, tr, eu.q, eu.r)
                    nearest_enemy_dist = min(nearest_enemy_dist, d)
            score = max(0, 10 - nearest_enemy_dist)

            tile_danger = danger.get((tq, tr), 0)
            if tile_danger > my_eff_str:
                score -= 25

        # Retreat: if in danger with no attack options, strongly prefer safer tiles
        if should_retreat:
            tile_danger = danger.get((tq, tr), 0)
            if tile_danger < current_danger:
                score += 25

        # Bonus for tiles that put the unit in attack range of an enemy unit
        unit_attack_range = defn.get("range", 1)
        for other in game.civs:
            if other.player_index == civ.player_index or other.is_eliminated:
                continue
            for eu in other.units:
                if eu.is_civilian:
                    continue
                d = hex_distance(tq, tr, eu.q, eu.r)
                if 1 <= d <= unit_attack_range:
                    score += 15

        if score > best_score:
            best_score = score
            best_action = ("move", tq, tr, cost)

    # 3. Score fortify (defense bonus, no healing)
    tile = game.tiles.get((unit.q, unit.r))
    in_city = tile and tile.city and tile.city.owner == civ.player_index
    fortify_score = 5
    if in_city:
        fortify_score += 10
    if role == "DEFENDER":
        fortify_score += 15

    if fortify_score > best_score:
        best_score = fortify_score
        best_action = ("fortify",)

    # 4. Score heal (recover HP, loses fortify bonus)
    hp_max = defn["hp_max"]
    if unit.hp < hp_max:
        missing = hp_max - unit.hp
        heal_xp_discount = min(0.3, unit.xp * 0.003)  # up to -30% at 100 XP
        heal_score = missing * (0.5 - heal_xp_discount)  # veterans fight hurt
        if in_city:
            heal_score += 5
        if heal_score > best_score:
            best_score = heal_score
            best_action = ("heal",)

    # Execute best action
    if not best_action:
        return

    if best_action[0] == "attack":
        _, tq, tr = best_action
        game.do_attack(unit, tq, tr)

    elif best_action[0] == "move":
        _, tq, tr, cost = best_action
        if not game.tiles.get((tq, tr)):
            return
        game.move_unit(unit, tq, tr, cost=cost)

    elif best_action[0] == "fortify":
        unit.fortified = True
        unit.healing = False
        unit.moves_left = 0

    elif best_action[0] == "heal":
        unit.healing = True
        unit.fortified = False
        unit.fortify_bonus = 0.0
        unit.moves_left = 0


# ---------------------------------------------------------------------------
# Component 6 — Settler Behavior
# ---------------------------------------------------------------------------
def _score_settle_tile(q, r, game, civ) -> float:
    from civ_game.map.terrain import TERRAIN_YIELDS

    # Hard reject: enemy territory or too close to any city
    tile = game.tiles.get((q, r))
    if tile and tile.owner is not None and tile.owner != civ.player_index:
        return -9999
    for oc in game.civs:
        for city in oc.cities:
            if hex_distance(q, r, city.q, city.r) <= 2:
                return -9999

    score = 0.0

    for (tq, tr) in hexes_in_range(q, r, 2):
        t = game.tiles.get((tq, tr))
        if not t or t.terrain == "ocean":
            continue
        y = TERRAIN_YIELDS.get(t.terrain, {})
        score += y.get("food", 0) * 3
        score += y.get("prod", 0) * 2
        score += y.get("gold", 0) * 1
        if t.resource:
            score += 10

    for other_civ in game.civs:
        for city in other_civ.cities:
            dist = hex_distance(q, r, city.q, city.r)
            if dist < 4:
                score -= (4 - dist) * 20

    return score


def _act_settler(game, civ, settler, flavors):
    if settler.moves_left == 0:
        return

    ok, _ = game.can_found_city(settler)
    if ok:
        found_score = _score_settle_tile(settler.q, settler.r, game, civ)
        if found_score > 15:
            game.found_city(settler)
            return
    reachable = get_reachable_tiles(settler, game.tiles, game.turn)

    best_score = -9999
    best_move = None

    for (tq, tr), cost in reachable.items():
        tile = game.tiles.get((tq, tr))
        if not tile or tile.terrain == "ocean" or tile.city:
            continue
        # Skip tiles that are in enemy territory or too close to existing cities
        if tile.owner is not None and tile.owner != civ.player_index:
            continue

        s = _score_settle_tile(tq, tr, game, civ)
        s *= flavors["expansion"]
        if s > best_score:
            best_score = s
            best_move = (tq, tr, cost)

    if best_move:
        tq, tr, cost = best_move
        game.move_unit(settler, tq, tr, cost=cost)


# ---------------------------------------------------------------------------
# Component 7 — Worker Behavior
# ---------------------------------------------------------------------------
def _act_worker(game, civ, worker):
    if worker.moves_left == 0 or worker.building_improvement:
        return

    from civ_game.entities.improvement import IMPROVEMENT_DEFS

    tile = game.tiles.get((worker.q, worker.r))
    if not tile:
        return

    best_imp = None
    best_gain = 0

    for key, defn in IMPROVEMENT_DEFS.items():
        terrain_ok = tile.terrain in defn.get("valid_terrain", [])
        gold_ok = (key == "mine" and getattr(tile, "resource", None) == "gold"
                   and tile.terrain in ("grassland", "plains"))
        if not terrain_ok and not gold_ok:
            continue
        if tile.improvement == key:
            continue
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue
        gain = sum(defn.get("yield_bonus", {}).values())
        if gain > best_gain:
            best_gain = gain
            best_imp = key

    if best_imp:
        game.start_improvement(worker, best_imp)
        return

    reachable = get_reachable_tiles(worker, game.tiles, game.turn)
    for (tq, tr) in reachable:
        t = game.tiles.get((tq, tr))
        if not t:
            continue
        if t.owner == civ.player_index and not t.improvement:
            game.move_unit(worker, tq, tr, cost=reachable[(tq, tr)])
            return


# ---------------------------------------------------------------------------
# Component 8 — City Production Scoring
# ---------------------------------------------------------------------------
def _act_city(game, civ, city, flavors, attack_target=None):
    if city.production_queue:
        return
    yields = compute_city_yields(city, game.tiles, civ)
    prod_pt = max(1, yields["prod"])

    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    military_need = max(0, city_count * 2 - military_count)
    ranged_count = sum(1 for u in civ.units
                       if not u.is_civilian and UNIT_DEFS[u.unit_type].get("ranged_strength"))
    ranged_ratio = ranged_count / military_count if military_count > 0 else 0.0

    # --- Strategic priority overrides (short-circuit normal scoring) ---

    # Priority 1: Enemy unit within 4 tiles → build the best available military unit now
    under_attack = any(
        hex_distance(u.q, u.r, city.q, city.r) <= 4
        for other in game.civs
        if other.player_index != civ.player_index and not other.is_eliminated
        for u in other.units if not u.is_civilian
    )
    if under_attack:
        best_mil_key, best_mil_str = None, -1
        for key, defn in UNIT_DEFS.items():
            if defn["type"] not in ("melee", "ranged"):
                continue
            req_tech = defn.get("requires_tech")
            if req_tech and req_tech not in civ.techs_researched:
                continue
            req_res = defn.get("requires_resource")
            if req_res and not any(
                t.resource == req_res and t.owner == civ.player_index
                for t in game.tiles.values()
            ):
                continue
            s = defn.get("ranged_strength") or defn["strength"]
            if s > best_mil_str:
                best_mil_str, best_mil_key = s, key
        if best_mil_key:
            city.production_queue.append(best_mil_key)
            return

    # Priority 2: No worker anywhere in the civ → build one
    has_worker = any(u.unit_type == "worker" for u in civ.units)
    worker_queued = any("worker" in c.production_queue for c in civ.cities if c is not city)
    if not has_worker and not worker_queued:
        city.production_queue.append("worker")
        return

    # Priority 3: Fewer than 3 cities and able to expand → settler
    if (city_count < 3
            and city.population >= 2
            and not any(u.unit_type == "settler" for u in civ.units)
            and not any("settler" in c.production_queue for c in civ.cities if c is not city)):
        city.production_queue.append("settler")
        return

    # --- Normal scoring below ---
    best_score = -9999
    best_key = None

    # Score units
    for key, defn in UNIT_DEFS.items():
        if defn["type"] == "civilian":
            if key == "settler":
                if city_count >= 4:
                    continue
                if city.population < 2:
                    continue
                if any(u.unit_type == "settler" for u in civ.units):
                    continue
                if any("settler" in c.production_queue for c in civ.cities if c is not city):
                    continue
                score = 55 * flavors["expansion"]
            elif key == "worker":
                has_worker = any(u.unit_type == "worker" and u.owner == civ.player_index
                                 for u in civ.units)
                score = 40 if not has_worker else 5
            else:
                continue
        else:
            req_tech = defn.get("requires_tech")
            if req_tech and req_tech not in civ.techs_researched:
                continue
            req_res = defn.get("requires_resource")
            if req_res and not any(
                t.resource == req_res and t.owner == civ.player_index
                for t in game.tiles.values()
            ):
                continue
            effective_str = defn.get("ranged_strength") or defn["strength"]
            base = 30 + effective_str * 1.5
            siege_urgency = 2.0 if attack_target else 1.0
            base += defn.get("bonus_vs_city", 0) * 5 * siege_urgency
            score = (base + military_need * 8) * flavors["military"]

            unit_is_ranged = bool(defn.get("ranged_strength"))
            if unit_is_ranged and ranged_ratio > 0.5:
                score *= 0.35  # too many ranged — strongly prefer melee
            elif not unit_is_ranged and ranged_ratio < 0.25:
                score *= 0.65  # too few ranged — softly nudge toward ranged

        turns = max(1, (get_item_cost(key) - city.production_progress + prod_pt - 1) // prod_pt)
        score -= turns * 0.5

        if score > best_score:
            best_score = score
            best_key = key

    # Score buildings
    for key, defn in BUILDING_DEFS.items():
        if key == "palace" or key in city.buildings:
            continue
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue

        effects = defn.get("effects", {})
        score = 0
        score += effects.get("food_per_turn",    0) * 8  * flavors["buildings"]
        score += effects.get("prod_per_turn",    0) * 7  * flavors["buildings"]
        score += effects.get("gold_per_turn",    0) * 6  * flavors["buildings"]
        score += effects.get("science_per_turn", 0) * 9  * flavors["science"]
        score += effects.get("culture_per_turn", 0) * 4  * flavors["buildings"]

        if "prod_bonus_hills" in effects:
            score += 20 * flavors["buildings"]

        if military_need > 2:
            score *= 0.6

        turns = max(1, (get_item_cost(key) - city.production_progress + prod_pt - 1) // prod_pt)
        score -= turns * 0.3

        if score > best_score:
            best_score = score
            best_key = key

    if best_key:
        city.production_queue.append(best_key)


# ---------------------------------------------------------------------------
# Component 9 — Research Scoring
# ---------------------------------------------------------------------------
def _pick_research(game, civ, flavors):
    if civ.current_research:
        return
    best_score = -9999
    best_tech = None

    for key, defn in TECH_DEFS.items():
        if key in civ.techs_researched:
            continue
        prereqs = defn.get("prerequisites", [])
        if not all(p in civ.techs_researched for p in prereqs):
            continue

        score = 0

        for unit_key in defn.get("unlocks_units", []):
            udef = UNIT_DEFS.get(unit_key, {})
            score += udef.get("strength", 5) * 2 * flavors["military"]

        for bld_key in defn.get("unlocks_buildings", []):
            bdef = BUILDING_DEFS.get(bld_key, {})
            effects = bdef.get("effects", {})
            score += effects.get("science_per_turn", 0) * 8 * flavors["science"]
            score += effects.get("gold_per_turn",    0) * 5 * flavors["buildings"]
            score += effects.get("prod_per_turn",    0) * 4 * flavors["buildings"]
            score += effects.get("food_per_turn",    0) * 4 * flavors["buildings"]

        for _ in defn.get("unlocks_improvements", []):
            score += 15 * flavors["buildings"]

        for res in defn.get("reveals_resources", []):
            has = any(t.resource == res and t.owner == civ.player_index
                      for t in game.tiles.values())
            if has:
                score += 25

        score -= defn["science_cost"] * 0.05

        if score > best_score:
            best_score = score
            best_tech = key

    if best_tech:
        civ.current_research = best_tech


# ---------------------------------------------------------------------------
# Component 10 — Gold / Buy Decisions
# ---------------------------------------------------------------------------
def _act_gold(game, civ, flavors):
    """Buy the strongest affordable unit in the most threatened city if urgent."""
    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    urgent_need = military_count < city_count

    if not urgent_need:
        return
    # Aggressive leaders buy with a smaller gold reserve; pacifist leaders hoard more.
    gold_threshold = int(80 / flavors["aggression"])
    if civ.gold < gold_threshold:
        return

    best_city = None
    best_threat = -1
    for city in civ.cities:
        tile = game.tiles.get((city.q, city.r))
        if tile and tile.unit is None:
            threat = sum(
                1 for oc in game.civs if oc.player_index != civ.player_index
                for u in oc.units
                if not u.is_civilian and hex_distance(u.q, u.r, city.q, city.r) <= 5
            )
            if threat > best_threat:
                best_threat = threat
                best_city = city

    if not best_city:
        return

    best_key = None
    best_str = 0
    for key, defn in UNIT_DEFS.items():
        if defn["type"] == "civilian":
            continue
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue
        gold_cost = get_item_cost(key) * 2
        if civ.gold >= gold_cost and defn["strength"] > best_str:
            best_str = defn["strength"]
            best_key = key

    if best_key:
        game.buy_item(best_city, best_key)


# ---------------------------------------------------------------------------
# Component 11 — Unit Upgrades
# ---------------------------------------------------------------------------
def _act_upgrades(game, civ, flavors):
    """Upgrade military units when affordable and the strength gain is worthwhile."""
    # Keep a gold reserve so we don't bankrupt ourselves upgrading
    gold_reserve = int(40 / flavors["aggression"])

    for unit in list(civ.units):
        if unit.is_civilian or unit.moves_left == 0:
            continue
        path = UNIT_UPGRADES.get(unit.unit_type)
        if not path:
            continue
        target_type, gold_cost = path
        if civ.gold - gold_cost < gold_reserve:
            continue
        tdef = UNIT_DEFS[target_type]
        # Only upgrade if the strength gain is meaningful
        old_str = UNIT_DEFS[unit.unit_type]["strength"]
        new_str = tdef["strength"]
        if new_str <= old_str:
            continue
        ok, _ = game.upgrade_unit(unit)
        if ok:
            # Unit spent its moves; continue to next unit
            continue


# ---------------------------------------------------------------------------
# Main AI Entry Point
# ---------------------------------------------------------------------------
def ai_take_turn(game, civ):
    """
    Execute a full turn for a CPU-controlled civilization.
    All actions execute instantly (no animation).
    """
    # Grand strategy — compute effective flavors for this turn
    flavors = _get_effective_flavors(game, civ)

    # Strategic layer
    danger        = _build_danger_map(game, civ)
    attack_target = _select_attack_target(game, civ, flavors)
    roles, defender_cities = _assign_roles(civ, danger, attack_target)

    # Muster check: effective attacker count vs city HP.
    # Melee units contribute min(1.5, max(1.0, strength/10)).
    # Ranged units contribute ranged_strength * city_bonus / 10 (unclamped).
    # min_attackers = round(city_hp / (50/3) + 1) → 4 at full HP, 1 at low HP.
    assault_ready = True
    if attack_target:
        MUSTER_RADIUS = 5
        REFERENCE_STRENGTH = 10
        min_attackers = round(attack_target.hp / (50 / 3) + 1)
        effective_count = 0.0
        melee_present = False
        for u in civ.units:
            if u.is_civilian or roles.get(id(u)) != "ATTACKER":
                continue
            if hex_distance(u.q, u.r, attack_target.q, attack_target.r) > MUSTER_RADIUS:
                continue
            udef = UNIT_DEFS[u.unit_type]
            city_mult = udef.get("bonus_vs_city", 1.0)
            u_xp_factor = 1.0 + u.xp * 0.01
            if udef.get("ranged_strength"):
                contrib = udef["ranged_strength"] * u_xp_factor * city_mult / REFERENCE_STRENGTH
            else:
                contrib = min(1.5, max(1.0, udef["strength"] * u_xp_factor / REFERENCE_STRENGTH))
                melee_present = True
            effective_count += contrib
        assault_ready = effective_count >= min_attackers and melee_present

    # Research
    _pick_research(game, civ, flavors)

    # City production
    for city in civ.cities:
        _act_city(game, civ, city, flavors, attack_target)

    # Upgrade units before acting (so they fight with new stats)
    _act_upgrades(game, civ, flavors)

    # Civilians first (settlers, workers), then military
    for unit in list(civ.units):
        if not unit.is_civilian:
            continue
        if unit.unit_type == "settler":
            _act_settler(game, civ, unit, flavors)
        elif unit.unit_type == "worker":
            _act_worker(game, civ, unit)

    for unit in list(civ.units):
        if unit.is_civilian:
            continue
        _act_military_unit(game, civ, unit, roles, defender_cities, attack_target, danger, flavors, assault_ready)

    # Gold / buy
    _act_gold(game, civ, flavors)
