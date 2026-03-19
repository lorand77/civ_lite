# DESIGN-AI.md — CPU AI for civ_lite_py (Option C: Threat-Aware Scored AI)

## Overview

This document is the complete, self-contained implementation guide for adding CPU-controlled
opponents. It can be used from a fresh context — no prior conversation needed.

**Approach:** Option C — Threat-Aware Scored AI
**Victory condition:** Domination only (own all original capitals). There are no science/culture
victory paths. The AI always pursues military dominance, but different leaders do so through
different styles (aggressive early rush vs. builder → conquer vs. tech → conquer).

**Design philosophy:**
- Every action is scored numerically; the AI picks the best score
- A strategic layer runs first each turn to set a danger map, unit roles, and attack target
- Roles constrain which actions are scored highly, producing coordinated unit behavior
- Four distinct leader personalities via flavor weights — same code, different behavior
- All AI decisions execute instantly within the same frame (no animation delays)

---

## Codebase Reference

### Key file paths
```
civ_lite_py/
  main.py                          ← game loop & event handling; _do_end_turn() is the hook point
  civ_game/
    game.py                        ← Game class; all action methods live here
    entities/
      civilization.py              ← Civilization dataclass
      unit.py                      ← Unit dataclass + get_reachable_tiles(), get_attackable_tiles()
      city.py                      ← City dataclass
    data/
      units.py                     ← UNIT_DEFS, UNIT_UPGRADES
      buildings.py                 ← BUILDING_DEFS
      techs.py                     ← TECH_DEFS
    map/
      hex_grid.py                  ← hex_distance(), hex_neighbors(), hexes_in_range()
      terrain.py                   ← TERRAIN_PASSABLE, TERRAIN_MOVE_COST, TERRAIN_YIELDS
    systems/
      production.py                ← get_item_cost(), complete_item()
      yields.py                    ← compute_city_yields(city, tiles, civ)
    ui/
      hud.py                       ← UIState dataclass
```

### Data model (fields the AI reads/writes)

**Civilization** (`civ_game/entities/civilization.py`):
```python
player_index: int          # 0–3
cities: list[City]
units: list[Unit]
gold: int
science: int
current_research: str | None
techs_researched: set[str]
original_capital: City | None
is_eliminated: bool
pending_messages: list[str]   # append here; shown to human at turn start
is_cpu: bool = False          # ADD THIS FIELD
```

**Unit** (`civ_game/entities/unit.py`):
```python
unit_type: str    # key into UNIT_DEFS
owner: int
q, r: int         # axial hex coords
hp: int
moves_left: int
fortified: bool
healing: bool
building_improvement: str | None
build_turns_left: int
is_civilian: bool  # property: True for settler/worker
```

**City** (`civ_game/entities/city.py`):
```python
name: str
q, r: int
owner: int
population: int
production_queue: list[str]
production_progress: int
buildings: list[str]
worked_tiles: list[tuple]
hp: int           # 0–50; city is captured when reduced to 0
```

**Tile** (value in `game.tiles: dict[(q,r) → Tile]`):
```python
terrain: str
owner: int | None
city: City | None
unit: Unit | None       # military unit
civilian: Unit | None   # civilian unit
resource: str | None
improvement: str | None
```

### Utility functions to reuse (DO NOT reimplement)

```python
# Pathfinding — returns {(q,r): move_cost}
from civ_game.entities.unit import get_reachable_tiles, get_attackable_tiles

# Hex geometry
from civ_game.map.hex_grid import hex_distance, hex_neighbors, hexes_in_range

# City yields
from civ_game.systems.yields import compute_city_yields

# Item costs
from civ_game.systems.production import get_item_cost

# Data dicts
from civ_game.data.units import UNIT_DEFS, UNIT_UPGRADES
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.data.techs import TECH_DEFS
from civ_game.map.terrain import TERRAIN_PASSABLE, TERRAIN_YIELDS
```

### Game action methods (call these, never mutate state directly)

```python
game.move_unit(unit, q, r, cost)         # move unit; cost from get_reachable_tiles
game.do_attack(attacker, target_q, r)    # returns message str; sets moves_left=0
game.found_city(settler)                 # settler founds city at its position
game.start_improvement(worker, key)      # key: "mine", "farm", "pasture"
game.buy_item(city, item_key)            # returns (bool, str); deducts gold
game.upgrade_unit(unit)                  # returns (bool, str)
game.end_turn()                          # processes end-of-turn; advances current_player
```

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `civ_game/systems/ai.py` | **CREATE** — all AI logic |
| `civ_game/ui/setup_screen.py` | **CREATE** — pre-game player setup UI |
| `civ_game/entities/civilization.py` | **MODIFY** — add `is_cpu: bool = False` field |
| `civ_game/game.py` | **MODIFY** — accept `cpu_flags` list in `__init__` |
| `main.py` | **MODIFY** — show setup screen before creating Game; loop CPU turns in `_do_end_turn()` |

---

## Leader Flavor System

Each civ leader has flavor weights that multiply into scoring functions.
Same AI code produces distinct playstyles.

```python
# In ai.py — top-level constant
LEADER_FLAVORS = {
    0: {  # Rome — balanced expansionist
        "military":  1.1,
        "expansion": 1.3,   # slightly more settlers
        "science":   0.9,
        "buildings": 1.0,
        "aggression": 1.0,  # attack threshold multiplier
    },
    1: {  # Greece — science-leaning, attacks late with better units
        "military":  0.7,
        "expansion": 0.9,
        "science":   1.3,
        "buildings": 1.3,
        "aggression": 0.7,  # waits for tech advantage before attacking
    },
    2: {  # Huns — aggressive early rusher
        "military":  1.8,
        "expansion": 1.2,
        "science":   0.5,
        "buildings": 0.6,
        "aggression": 1.8,  # attacks at lower strength ratio
    },
    3: {  # Babylon — builder, attacks with bought army
        "military":  0.8,
        "expansion": 0.8,
        "science":   1.8,
        "buildings": 1.7,
        "aggression": 0.9,
    },
}
```

---

## Component 1 — Danger Map

Computes how much enemy military threat exists on each tile.
Built once at the start of each CPU turn.

```python
def _build_danger_map(game, civ) -> dict:
    """
    Returns {(q, r): danger_value} where danger_value is the sum of
    strengths of all enemy military units that could reach that tile
    in one turn (approximated by hex_distance <= moves).
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
            # Mark all tiles within move range as dangerous
            for (q, r), tile in game.tiles.items():
                if hex_distance(unit.q, unit.r, q, r) <= move_range:
                    danger[(q, r)] = danger.get((q, r), 0) + strength
    return danger
```

---

## Component 2 — City Threat Assessment

Uses the danger map to score each city's vulnerability.

```python
def _city_threat(city, danger) -> int:
    """Sum of danger values within radius 3 of city."""
    total = 0
    for (q, r), val in danger.items():
        if hex_distance(city.q, city.r, q, r) <= 3:
            total += val
    return total
```

---

## Component 3 — Attack Target Selection

Picks the single best enemy city to focus on this turn.
Returns None if the AI should not attack (too weak).

```python
def _select_attack_target(game, civ) -> object:  # City | None
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
        # Default threshold: 1.5x. Huns (aggression=1.8) attack at 2.7x disadvantage.
        # Greece (aggression=0.7) only attacks at 1.05x advantage.
        max_enemy_ratio = 1.0 + flavors["aggression"] * 0.5
        if my_strength == 0 or enemy_strength > my_strength * max_enemy_ratio:
            continue

        for city in other.cities:
            score = 0

            # Prefer power advantage
            score += (my_strength - enemy_strength) * 2

            # Prefer damaged cities (easier to take)
            score += (50 - city.hp) * 1.5

            # Prefer original capitals (winning condition)
            if city == other.original_capital:
                score += 40

            # Prefer closer cities
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
```

---

## Component 4 — Unit Role Assignment

Assigns each military unit a role based on strategic situation.
Roles constrain how scoring functions weight actions.

```python
def _assign_roles(civ, danger, attack_target) -> dict:
    """
    Returns {unit_id: role_str} where role is one of:
      "DEFENDER"  — stay near a threatened city
      "ATTACKER"  — march toward attack_target
      "PATROL"    — move toward borders, fortify if idle
    """
    roles = {}

    # Find cities under significant threat
    threatened_cities = [
        c for c in civ.cities
        if _city_threat(c, danger) > 15
    ]

    military_units = [u for u in civ.units if not u.is_civilian]

    # Sort by proximity to nearest threatened city
    def nearest_threat_dist(unit):
        if not threatened_cities:
            return 999
        return min(hex_distance(unit.q, unit.r, c.q, c.r)
                   for c in threatened_cities)

    military_units.sort(key=nearest_threat_dist)

    # Assign defenders: one unit per threatened city, picking closest unit
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
            roles[id(unit) + 10000] = nearest  # store assigned city reference
            assigned_defender_cities.add(id(nearest))

    # Remaining units: ATTACKER if target exists, else PATROL
    for unit in military_units:
        if id(unit) not in roles:
            roles[id(unit)] = "ATTACKER" if attack_target else "PATROL"

    return roles
```

Note: `roles[id(unit) + 10000]` stores the assigned city for DEFENDER units.
Retrieve with `roles.get(id(unit) + 10000)`.

---

## Component 5 — Unit Action Execution

Main function for each military unit. Scores available actions, executes highest.

```python
def _act_military_unit(game, civ, unit, roles, attack_target, danger):
    if unit.moves_left == 0:
        return

    role = roles.get(id(unit), "PATROL")
    defn = UNIT_DEFS[unit.unit_type]

    # --- Score all candidate actions ---
    best_score = -9999
    best_action = None  # ("attack", q, r) | ("move", q, r, cost) | ("fortify",) | ("heal",)

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

        if target_unit:
            t_defn = UNIT_DEFS[target_unit.unit_type]
            t_str = t_defn["strength"]
            my_str = defn["strength"]
            hp_ratio = unit.hp / defn["hp_max"]

            score += (my_str - t_str) * 4        # prefer winnable fights
            score += (100 - target_unit.hp) * 0.3 # prefer wounded targets
            score -= (1.0 - hp_ratio) * 30        # don't attack when badly wounded

            if target_city and target_city.owner != civ.player_index:
                score += 20                        # bonus: attack is also on a city tile

        elif target_city and target_city.owner != civ.player_index:
            score += 30
            score += (50 - target_city.hp) * 0.5  # prefer damaged cities
            if target_city == attack_target:
                score += 25                        # matches our strategic target

        # Role modifiers
        if role == "DEFENDER":
            score *= 0.4    # defenders rarely attack unless it's right next to them
        elif role == "ATTACKER" and target_city == attack_target:
            score *= 1.5    # attackers strongly prefer hitting the target city

        # Apply aggression flavor
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
                score = (current_dist - new_dist) * 15  # reward closing on city
                # Bonus for being ON the city tile
                tile = game.tiles.get((tq, tr))
                if tile and tile.city == assigned_city:
                    score += 20

        elif role == "ATTACKER" and attack_target:
            current_dist = hex_distance(unit.q, unit.r, attack_target.q, attack_target.r)
            new_dist = hex_distance(tq, tr, attack_target.q, attack_target.r)
            score = (current_dist - new_dist) * 12

            # Don't charge alone into high-danger tiles
            tile_danger = danger.get((tq, tr), 0)
            if tile_danger > defn["strength"] * 1.5:
                score -= 40

        else:  # PATROL
            # Move toward nearest enemy
            nearest_enemy_dist = 999
            for other in game.civs:
                if other.player_index == civ.player_index or other.is_eliminated:
                    continue
                for eu in other.units:
                    d = hex_distance(tq, tr, eu.q, eu.r)
                    nearest_enemy_dist = min(nearest_enemy_dist, d)
            score = max(0, 10 - nearest_enemy_dist)

            # Avoid high-danger tiles while patrolling
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
        fortify_score += 20  # injured: prefer to stop and heal

    if fortify_score > best_score:
        best_score = fortify_score
        best_action = ("fortify",)

    # --- Execute best action ---
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
```

---

## Component 6 — Settler Behavior

Settlers find the best unclaimed tile and move toward it.

```python
def _act_settler(game, civ, settler):
    if settler.moves_left == 0:
        return

    # Can we found here right now?
    tile = game.tiles.get((settler.q, settler.r))
    if tile and tile.terrain != "ocean" and tile.city is None:
        # Score this tile as a found location
        found_score = _score_settle_tile(settler.q, settler.r, game, civ)
        if found_score > 30:   # threshold: don't found on terrible land
            game.found_city(settler)
            return

    # Find best reachable tile to move toward
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


def _score_settle_tile(q, r, game, civ) -> float:
    from civ_game.map.terrain import TERRAIN_YIELDS, RESOURCES
    score = 0.0

    # Sum yields of all tiles within radius 2
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

    # Penalty: too close to existing city (own or enemy)
    for other_civ in game.civs:
        for city in other_civ.cities:
            dist = hex_distance(q, r, city.q, city.r)
            if dist < 4:
                score -= (4 - dist) * 20

    return score
```

---

## Component 7 — Worker Behavior

Workers build improvements on worked tiles, prioritizing yield gain.

```python
def _act_worker(game, civ, worker):
    if worker.moves_left == 0 or worker.building_improvement:
        return  # already building something

    from civ_game.entities.improvement import IMPROVEMENT_DEFS

    tile = game.tiles.get((worker.q, worker.r))
    if not tile:
        return

    # Try to build an improvement on the current tile
    best_imp = None
    best_gain = 0

    for key, defn in IMPROVEMENT_DEFS.items():
        if tile.terrain not in defn.get("valid_terrain", []):
            continue
        if tile.improvement == key:
            continue  # already built
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue
        # Estimate yield gain
        gain = sum(defn.get("yield_bonus", {}).values())
        if gain > best_gain:
            best_gain = gain
            best_imp = key

    if best_imp:
        game.start_improvement(worker, best_imp)
        return

    # No useful improvement here — move to nearest unimproved worked tile
    reachable = get_reachable_tiles(worker, game.tiles, game.turn)
    for (tq, tr) in reachable:
        t = game.tiles.get((tq, tr))
        if not t:
            continue
        if t.owner == civ.player_index and not t.improvement:
            game.move_unit(worker, tq, tr, cost=reachable[(tq, tr)])
            return
```

---

## Component 8 — City Production Scoring

Called when a city's queue is empty. Scores all available items and queues the best one.

```python
def _act_city(game, civ, city):
    if city.production_queue:
        return  # already has something queued

    flavors = LEADER_FLAVORS[civ.player_index]
    yields = compute_city_yields(city, game.tiles, civ)
    prod_pt = max(1, yields["prod"])

    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    military_need = max(0, city_count * 2 - military_count)  # target: 2 military per city

    best_score = -9999
    best_key = None

    # Score units
    for key, defn in UNIT_DEFS.items():
        if defn["type"] == "civilian":
            if key == "settler":
                if city_count >= 4:
                    continue  # don't over-expand
                if city.population < 2:
                    continue  # don't starve the city
                score = 55 * flavors["expansion"]
            elif key == "worker":
                has_worker = any(u.unit_type == "worker" and u.owner == civ.player_index
                                 for u in civ.units)
                score = 40 if not has_worker else 5
            else:
                continue
        else:
            # Military unit
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

        # Slight penalty for items that take very long to build
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

        # Special case: forge gives prod on hills — hard to score generically
        if "prod_bonus_hills" in effects:
            score += 20 * flavors["buildings"]

        # Penalty for expensive buildings when military is urgent
        if military_need > 2:
            score *= 0.6

        turns = max(1, (get_item_cost(key) - city.production_progress + prod_pt - 1) // prod_pt)
        score -= turns * 0.3

        if score > best_score:
            best_score = score
            best_key = key

    if best_key:
        city.production_queue.append(best_key)
```

---

## Component 9 — Research Scoring

Called when civ has no current research.

```python
def _pick_research(game, civ):
    if civ.current_research:
        return

    flavors = LEADER_FLAVORS[civ.player_index]
    best_score = -9999
    best_tech = None

    for key, defn in TECH_DEFS.items():
        if key in civ.techs_researched:
            continue
        # Check prerequisites
        prereqs = defn.get("prerequisites", [])
        if not all(p in civ.techs_researched for p in prereqs):
            continue

        score = 0

        # Value unlocked units by their strength
        for unit_key in defn.get("unlocks_units", []):
            udef = UNIT_DEFS.get(unit_key, {})
            score += udef.get("strength", 5) * 2 * flavors["military"]

        # Value unlocked buildings by their effects
        for bld_key in defn.get("unlocks_buildings", []):
            bdef = BUILDING_DEFS.get(bld_key, {})
            effects = bdef.get("effects", {})
            score += effects.get("science_per_turn", 0) * 8 * flavors["science"]
            score += effects.get("gold_per_turn",    0) * 5 * flavors["buildings"]
            score += effects.get("prod_per_turn",    0) * 4 * flavors["buildings"]
            score += effects.get("food_per_turn",    0) * 4 * flavors["buildings"]

        # Value improvements (especially if civ has relevant resources)
        for imp_key in defn.get("unlocks_improvements", []):
            score += 15 * flavors["buildings"]

        # Bonus if revealed resource exists in civ territory
        for res in defn.get("reveals_resources", []):
            has = any(t.resource == res and t.owner == civ.player_index
                      for t in game.tiles.values())
            if has:
                score += 25

        # Slight cost penalty
        score -= defn["science_cost"] * 0.05

        if score > best_score:
            best_score = score
            best_tech = key

    if best_tech:
        civ.current_research = best_tech
```

---

## Component 10 — Gold / Buy Decisions

After all units and cities have acted, check if buying something is worthwhile.

```python
def _act_gold(game, civ):
    """
    If gold is plentiful and military is urgently needed, buy the strongest
    available unit in the most threatened city.
    """
    flavors = LEADER_FLAVORS[civ.player_index]
    military_count = sum(1 for u in civ.units if not u.is_civilian)
    city_count = len(civ.cities)
    urgent_need = military_count < city_count  # fewer than 1 unit per city = urgent

    if not urgent_need:
        return
    if civ.gold < 80:   # minimum meaningful purchase
        return

    # Find the most threatened city with space to receive a unit
    best_city = None
    best_threat = -1
    for city in civ.cities:
        tile = game.tiles.get((city.q, city.r))
        if tile and tile.unit is None:  # tile is free for a unit
            # Use a simple danger proxy: any enemy within 5 hexes
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

    # Find best unit we can afford
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
```

---

## Main AI Entry Point

The top-level function called once per CPU civ per turn.

```python
def ai_take_turn(game, civ):
    """
    Execute a full turn for a CPU-controlled civilization.
    All actions execute instantly (no animation).
    """
    # === Strategic layer ===
    danger       = _build_danger_map(game, civ)
    attack_target = _select_attack_target(game, civ)
    roles        = _assign_roles(civ, danger, attack_target)

    # === Research ===
    _pick_research(game, civ)

    # === City production ===
    for city in civ.cities:
        _act_city(game, civ, city)

    # === Units ===
    # Process in consistent order: settlers first, workers, military last
    for unit in list(civ.units):  # copy: list may mutate if unit is removed
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

    # === Gold / buy ===
    _act_gold(game, civ)
```

---

## Modification 1 — Player Setup Screen (civ_game/ui/setup_screen.py)

A new full-screen UI shown **before** the Game object is created. The player toggles
each of the 4 civs between Human and CPU, then clicks Start Game. Returns a list of
4 bools (`cpu_flags`) that is passed to `Game.__init__`.

### Visual layout (centered panel, ~500×380px on the 1850×1000 screen)

```
┌─────────────────────────────────────┐
│         CivPy — Player Setup        │
│                                     │
│  ■  Rome          [  Human  ]       │
│  ■  Greece        [   CPU   ]       │
│  ■  The Huns      [   CPU   ]       │
│  ■  Babylon       [   CPU   ]       │
│                                     │
│             [ Start Game ]          │
└─────────────────────────────────────┘
```

- Each row has: colored square swatch + civ name + toggle button
- Toggle button label/color: **Human** = blue-tinted `(40, 80, 140)` / **CPU** = gray `(70, 70, 90)`
- Clicking the toggle button flips the state for that player
- Start Game button: green, centered at bottom of panel

### Code — civ_game/ui/setup_screen.py

```python
import pygame
import sys

SCREEN_W = 1850
SCREEN_H = 1000

PANEL_W  = 500
PANEL_H  = 380
PANEL_X  = (SCREEN_W - PANEL_W) // 2
PANEL_Y  = (SCREEN_H - PANEL_H) // 2

# Matches game.py constants
PLAYER_NAMES  = ["Rome", "Greece", "The Huns", "Babylon"]
PLAYER_COLORS = [(220, 50, 50), (50, 100, 220), (50, 180, 50), (220, 180, 50)]

COLOR_BG      = (20, 20, 30)
COLOR_PANEL   = (30, 30, 45)
COLOR_BORDER  = (100, 100, 140)
COLOR_TEXT    = (230, 230, 230)
COLOR_HUMAN   = (40,  80, 140)
COLOR_HUMAN_H = (60, 110, 190)
COLOR_CPU     = (70,  70,  90)
COLOR_CPU_H   = (100, 100, 120)
COLOR_START   = (50, 110, 50)
COLOR_START_H = (70, 150, 70)

_font_cache = {}

def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def run_setup_screen(screen) -> list:
    """
    Blocking loop — renders the player setup screen and returns a list of
    4 bools: cpu_flags[i] = True means player i is CPU-controlled.
    Default: player 0 Human, players 1-3 CPU.
    """
    is_cpu = [False, True, True, True]
    clock  = pygame.time.Clock()

    while True:
        mouse = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check toggle buttons
                for i in range(4):
                    btn_rect = _toggle_rect(i)
                    if btn_rect.collidepoint(event.pos):
                        is_cpu[i] = not is_cpu[i]
                # Check Start button
                if _start_rect().collidepoint(event.pos):
                    return is_cpu

        _render(screen, is_cpu, mouse)
        pygame.display.flip()
        clock.tick(60)


def _row_y(player_index) -> int:
    """Top y of a player row inside the panel."""
    return PANEL_Y + 80 + player_index * 64


def _toggle_rect(player_index) -> pygame.Rect:
    return pygame.Rect(PANEL_X + PANEL_W - 140, _row_y(player_index) + 4, 120, 36)


def _start_rect() -> pygame.Rect:
    return pygame.Rect(PANEL_X + PANEL_W // 2 - 100, PANEL_Y + PANEL_H - 66, 200, 44)


def _render(screen, is_cpu, mouse):
    screen.fill(COLOR_BG)

    # Panel
    pygame.draw.rect(screen, COLOR_PANEL, (PANEL_X, PANEL_Y, PANEL_W, PANEL_H))
    pygame.draw.rect(screen, COLOR_BORDER, (PANEL_X, PANEL_Y, PANEL_W, PANEL_H), 2)

    # Title
    title = _font(34).render("CivPy  —  Player Setup", True, COLOR_TEXT)
    screen.blit(title, title.get_rect(centerx=PANEL_X + PANEL_W // 2, top=PANEL_Y + 18))

    # Divider
    pygame.draw.line(screen, COLOR_BORDER,
                     (PANEL_X + 16, PANEL_Y + 60), (PANEL_X + PANEL_W - 16, PANEL_Y + 60), 1)

    # Player rows
    for i in range(4):
        row_y = _row_y(i)

        # Color swatch
        pygame.draw.rect(screen, PLAYER_COLORS[i], (PANEL_X + 24, row_y + 8, 22, 22))

        # Name
        name_surf = _font(26).render(PLAYER_NAMES[i], True, PLAYER_COLORS[i])
        screen.blit(name_surf, (PANEL_X + 60, row_y + 10))

        # Toggle button
        btn_rect = _toggle_rect(i)
        if is_cpu[i]:
            btn_color = COLOR_CPU_H if btn_rect.collidepoint(mouse) else COLOR_CPU
            label = "CPU"
        else:
            btn_color = COLOR_HUMAN_H if btn_rect.collidepoint(mouse) else COLOR_HUMAN
            label = "Human"
        pygame.draw.rect(screen, btn_color, btn_rect, border_radius=4)
        pygame.draw.rect(screen, COLOR_BORDER, btn_rect, 1, border_radius=4)
        lbl = _font(22).render(label, True, COLOR_TEXT)
        screen.blit(lbl, lbl.get_rect(center=btn_rect.center))

    # Start button
    sr = _start_rect()
    sc = COLOR_START_H if sr.collidepoint(mouse) else COLOR_START
    pygame.draw.rect(screen, sc, sr, border_radius=5)
    pygame.draw.rect(screen, COLOR_BORDER, sr, 1, border_radius=5)
    start_lbl = _font(26).render("Start Game", True, COLOR_TEXT)
    screen.blit(start_lbl, start_lbl.get_rect(center=sr.center))
```

---

## Modification 2 — civilization.py

Add `is_cpu` field:

```python
# In the Civilization @dataclass, add after is_eliminated:
is_cpu: bool = False
```

---

## Modification 3 — game.py

Accept `cpu_flags` in `__init__` instead of hardcoding players 1–3 as CPU.
This lets the setup screen control which players are human vs CPU.

```python
# Change signature:
def __init__(self, num_players=4, map_cols=MAP_COLS, map_rows=MAP_ROWS,
             seed=None, cpu_flags=None):
    ...
    self.civs = self._create_civs()

    # Apply CPU flags from setup screen
    # cpu_flags is a list of bools, one per player.
    # Default (None): all players except 0 are CPU.
    if cpu_flags is not None:
        for i, flag in enumerate(cpu_flags[:self.num_players]):
            self.civs[i].is_cpu = flag
    else:
        for i in range(1, self.num_players):
            self.civs[i].is_cpu = True
    ...
```

Remove the old block that unconditionally marked players 1–3 as CPU.

---

## Modification 4 — main.py

Two changes needed:

### 4a — Show setup screen before creating the game

In `main()`, replace:
```python
game = Game(num_players=4, map_cols=32, map_rows=20, seed=None)
```
with:
```python
from civ_game.ui.setup_screen import run_setup_screen
cpu_flags = run_setup_screen(screen)   # blocks until player clicks Start
game = Game(num_players=4, map_cols=32, map_rows=20, seed=None, cpu_flags=cpu_flags)
```

### 4b — Loop CPU turns after human ends their turn

In `_do_end_turn()`, after the existing code, add the CPU auto-play loop.

Current `_do_end_turn` structure (lines 74–99):
```python
def _do_end_turn(game, ui_state):
    from civ_game.map.hex_grid import hex_to_pixel, HEX_SIZE
    game.end_turn()
    ui_state.deselect()
    ui_state.turn_banner_timer = 120

    # ... camera centering ...
    # ... pending_messages queuing ...
```

**Replace** the function body with:

```python
def _do_end_turn(game, ui_state):
    from civ_game.map.hex_grid import hex_to_pixel, HEX_SIZE
    from civ_game.systems.ai import ai_take_turn

    game.end_turn()
    ui_state.deselect()

    # Auto-play all consecutive CPU turns before showing turn banner
    while (not game.winner
           and game.current_civ().is_cpu):
        # Collect CPU messages so human sees them after their turn banner
        ai_take_turn(game, game.current_civ())
        game.end_turn()

    # Now current_player is human (or game is won) — show turn banner
    ui_state.turn_banner_timer = 120

    # Center camera on the new (human) player's capital
    new_civ = game.current_civ()
    cap = new_civ.original_capital
    if cap:
        px, py = hex_to_pixel(cap.q, cap.r, hex_size=HEX_SIZE)
        game.camera.center_on_pixel(px, py)
    else:
        settler = next((u for u in new_civ.units if u.unit_type == "settler"), None)
        if settler:
            px, py = hex_to_pixel(settler.q, settler.r, hex_size=HEX_SIZE)
            game.camera.center_on_pixel(px, py)

    # Queue start-of-turn messages (human player only)
    if new_civ.pending_messages:
        ui_state.queued_message = "\n".join(new_civ.pending_messages)
        new_civ.pending_messages.clear()
    if new_civ.research_just_completed:
        ui_state.auto_open_tech = True
        new_civ.research_just_completed = False
```

---

## Complete File Outline — civ_game/systems/ai.py

```
ai.py
├── LEADER_FLAVORS dict
├── _build_danger_map(game, civ) -> dict
├── _city_threat(city, danger) -> int
├── _select_attack_target(game, civ) -> City | None
├── _assign_roles(civ, danger, attack_target) -> dict
├── _act_military_unit(game, civ, unit, roles, attack_target, danger)
├── _score_settle_tile(q, r, game, civ) -> float
├── _act_settler(game, civ, settler)
├── _act_worker(game, civ, worker)
├── _act_city(game, civ, city)
├── _pick_research(game, civ)
├── _act_gold(game, civ)
└── ai_take_turn(game, civ)          ← public entry point
```

Total: approximately 280–320 lines.

---

## Known Limitations (by design — not bugs)

- **No multi-turn planning**: The AI doesn't pre-commit to "build 3 units then attack." It re-evaluates every turn. Military buildup happens naturally because `_act_city` keeps queuing units when `military_need > 0`.
- **No inter-civ diplomacy**: Target selection is purely based on strength ratio and proximity, not "who is a bigger threat to my long-term position."
- **Single victory path**: Only domination exists; the AI always builds toward military strength regardless of flavor (science/builder flavors just delay military, they don't pursue alternate wins).
- **No multi-unit siege coordination**: Role system prevents premature lone attacks, but doesn't actively assemble a specific stack before attacking. Units converge naturally from their ATTACKER movement scores.

---

## Verification Steps

```
cd /workspace/civ_lite_py && python main.py
```

1. **Setup screen appears**: Before the map loads, a panel shows 4 player rows each
   with a Human/CPU toggle. Default: Rome = Human, others = CPU.

2. **Toggles work**: Clicking a toggle button switches Human ↔ CPU. Color and label
   update immediately.

3. **Start Game launches correctly**: Clicking Start Game creates the game with the
   chosen configuration and shows the map.

4. **All-human hot-seat**: Set all 4 to Human. Each player takes turns manually with
   no auto-play. Turn banner cycles normally.

5. **All-CPU watch mode**: Set all 4 to CPU. After clicking Start, hitting End Turn
   once should simulate all turns until a winner (no human banner wait needed —
   the `while is_cpu` loop runs to game end).

6. **CPU takes turns**: With default setup (Rome human, others CPU), press Enter →
   turn banner should cycle through CPU players instantly and return to Rome.

7. **CPU founds cities**: After ~5–10 turns, CPU civs should have founded at least
   1 city each.

8. **CPU trains units**: After ~15 turns, CPU civs should have 2+ military units each.

9. **CPU attacks**: After ~20–30 turns, aggressive civs (Huns) should attack human
   or neighboring civs if they have a strength advantage.

10. **CPU researches techs**: Observe CPU units upgrading to archer/spearman/swordsman
    class over time.

11. **Personality differences**: Huns should be noticeably more aggressive than Babylon
   (attacks earlier, fewer buildings). Greece should have more science buildings.
```
