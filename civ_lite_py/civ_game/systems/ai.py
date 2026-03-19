"""
CPU AI — Option C: Threat-Aware Scored AI
Each CPU civ calls ai_take_turn(game, civ) once per turn.
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
        "expansion":  1.3,
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
# Component 1 — Danger Map
# ---------------------------------------------------------------------------
def _build_danger_map(game, civ) -> dict:
    """
    Returns {(q, r): danger_value} — sum of enemy unit strengths that could
    reach each tile in one move (approximated by hex_distance <= moves).
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
            for (q, r) in game.tiles:
                if hex_distance(unit.q, unit.r, q, r) <= move_range:
                    danger[(q, r)] = danger.get((q, r), 0) + strength
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
def _select_attack_target(game, civ):
    """Pick the single best enemy city to focus on. Returns None if too weak."""
    flavors = LEADER_FLAVORS[civ.player_index]

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
def _assign_roles(civ, danger, attack_target) -> dict:
    """
    Returns {unit_id: role_str} plus {unit_id + 10000: assigned_city} for defenders.
    Roles: "DEFENDER", "ATTACKER", "PATROL"
    """
    roles = {}

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
            roles[id(unit) + 10000] = nearest
            assigned_defender_cities.add(id(nearest))

    for unit in military_units:
        if id(unit) not in roles:
            roles[id(unit)] = "ATTACKER" if attack_target else "PATROL"

    return roles


# ---------------------------------------------------------------------------
# Component 5 — Military Unit Action
# ---------------------------------------------------------------------------
def _act_military_unit(game, civ, unit, roles, attack_target, danger):
    if unit.moves_left == 0:
        return

    role = roles.get(id(unit), "PATROL")
    defn = UNIT_DEFS[unit.unit_type]

    best_score = -9999
    best_action = None  # ("attack", q, r) | ("move", q, r, cost) | ("fortify",)

    attackable = get_attackable_tiles(unit, game.tiles)
    reachable = get_reachable_tiles(unit, game.tiles, game.turn)

    # 1. Score attack options
    for (tq, tr) in attackable:
        tile = game.tiles.get((tq, tr))
        if not tile:
            continue

        target_unit = tile.unit or tile.civilian
        target_city = tile.city

        score = 0

        if target_unit and target_unit.owner != civ.player_index:
            t_defn = UNIT_DEFS[target_unit.unit_type]
            t_str = t_defn["strength"]
            my_str = defn["strength"]
            hp_ratio = unit.hp / defn["hp_max"]

            score += (my_str - t_str) * 4
            score += (100 - target_unit.hp) * 0.3
            score -= (1.0 - hp_ratio) * 30

            if target_city and target_city.owner != civ.player_index:
                score += 20

        elif target_city and target_city.owner != civ.player_index and not (tile.unit and tile.unit.owner != civ.player_index):
            score += 30
            score += (50 - target_city.hp) * 0.5
            if target_city == attack_target:
                score += 25
        else:
            continue  # nothing valid to attack here

        # Role modifiers
        if role == "DEFENDER":
            score *= 0.4
        elif role == "ATTACKER" and target_city == attack_target:
            score *= 1.5

        score *= LEADER_FLAVORS[civ.player_index]["military"]

        if score > best_score:
            best_score = score
            best_action = ("attack", tq, tr)

    # 2. Score movement options
    for (tq, tr), cost in reachable.items():
        score = 0

        if role == "DEFENDER":
            assigned_city = roles.get(id(unit) + 10000)
            if assigned_city:
                current_dist = hex_distance(unit.q, unit.r, assigned_city.q, assigned_city.r)
                new_dist = hex_distance(tq, tr, assigned_city.q, assigned_city.r)
                score = (current_dist - new_dist) * 15
                tile = game.tiles.get((tq, tr))
                if tile and tile.city == assigned_city:
                    score += 20

        elif role == "ATTACKER" and attack_target:
            current_dist = hex_distance(unit.q, unit.r, attack_target.q, attack_target.r)
            new_dist = hex_distance(tq, tr, attack_target.q, attack_target.r)
            score = (current_dist - new_dist) * 12

            tile_danger = danger.get((tq, tr), 0)
            if tile_danger > defn["strength"] * 1.5:
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
            if tile_danger > defn["strength"]:
                score -= 25

        if score > best_score:
            best_score = score
            best_action = ("move", tq, tr, cost)

    # 3. Score fortify
    fortify_score = 5
    tile = game.tiles.get((unit.q, unit.r))
    if tile and tile.city and tile.city.owner == civ.player_index:
        fortify_score += 10
    if role == "DEFENDER":
        fortify_score += 15
    if unit.hp < 50:
        fortify_score += 20

    if fortify_score > best_score:
        best_score = fortify_score
        best_action = ("fortify",)

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
        unit.moves_left = 0


# ---------------------------------------------------------------------------
# Component 6 — Settler Behavior
# ---------------------------------------------------------------------------
def _score_settle_tile(q, r, game, civ) -> float:
    from civ_game.map.terrain import TERRAIN_YIELDS, RESOURCES
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


def _act_settler(game, civ, settler):
    if settler.moves_left == 0:
        return

    tile = game.tiles.get((settler.q, settler.r))
    if tile and tile.terrain != "ocean" and tile.city is None:
        found_score = _score_settle_tile(settler.q, settler.r, game, civ)
        if found_score > 30:
            game.found_city(settler)
            return

    flavors = LEADER_FLAVORS[civ.player_index]
    reachable = get_reachable_tiles(settler, game.tiles, game.turn)

    best_score = -9999
    best_move = None

    for (tq, tr), cost in reachable.items():
        tile = game.tiles.get((tq, tr))
        if not tile or tile.terrain == "ocean" or tile.city:
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
        if tile.terrain not in defn.get("valid_terrain", []):
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
def _act_city(game, civ, city):
    if city.production_queue:
        return

    flavors = LEADER_FLAVORS[civ.player_index]
    yields = compute_city_yields(city, game.tiles, civ)
    prod_pt = max(1, yields["prod"])

    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    military_need = max(0, city_count * 2 - military_count)

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
            base = 30 + defn["strength"] * 1.5
            score = (base + military_need * 8) * flavors["military"]

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
def _pick_research(game, civ):
    if civ.current_research:
        return

    flavors = LEADER_FLAVORS[civ.player_index]
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

        for imp_key in defn.get("unlocks_improvements", []):
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
def _act_gold(game, civ):
    """Buy the strongest affordable unit in the most threatened city if urgent."""
    flavors = LEADER_FLAVORS[civ.player_index]
    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    urgent_need = military_count < city_count

    if not urgent_need:
        return
    if civ.gold < 80:
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
# Main AI Entry Point
# ---------------------------------------------------------------------------
def ai_take_turn(game, civ):
    """
    Execute a full turn for a CPU-controlled civilization.
    All actions execute instantly (no animation).
    """
    # Strategic layer
    danger        = _build_danger_map(game, civ)
    attack_target = _select_attack_target(game, civ)
    roles         = _assign_roles(civ, danger, attack_target)

    # Research
    _pick_research(game, civ)

    # City production
    for city in civ.cities:
        _act_city(game, civ, city)

    # Civilians first (settlers, workers), then military
    for unit in list(civ.units):
        if not unit.is_civilian:
            continue
        if unit.unit_type == "settler":
            _act_settler(game, civ, unit)
        elif unit.unit_type == "worker":
            _act_worker(game, civ, unit)

    for unit in list(civ.units):
        if unit.is_civilian:
            continue
        _act_military_unit(game, civ, unit, roles, attack_target, danger)

    # Gold / buy
    _act_gold(game, civ)
