import numpy as np
from civ_game.map.hex_grid import HEX_SIZE, hex_to_pixel, hexes_in_range
from civ_game.map.generator import generate_map
from civ_game.map.terrain import TERRAIN_PASSABLE, TERRAIN_YIELDS, RESOURCES
from civ_game.entities.civilization import Civilization
from civ_game.entities.unit import Unit
from civ_game.entities.city import City, auto_assign_worked_tiles
from civ_game.data.units import UNIT_DEFS
from civ_game.systems.yields import compute_city_yields

MAP_COLS = 32
MAP_ROWS = 20
SCREEN_W = 1850
SCREEN_H = 1000
HUD_HEIGHT = 180

PLAYER_NAMES = ["Rome", "Greece", "The Huns", "Babylon"]
PLAYER_COLORS = [
    (220, 50,  50),
    (50,  100, 220),
    (50,  180, 50),
    (220, 180, 50),
]

CITY_NAMES = [
    ["Rome",    "Florence", "Venice",  "Genoa",   "Naples"],
    ["Athens",  "Sparta",   "Corinth", "Delphi",  "Argos"],
    ["Attila's Court",   "Pannonia",     "Germania",   "Gothia",  "Scythia"],
    ["Babylon", "Ur", "Nineveh", "Kish",    "Akkad"],
]


class Camera:
    def __init__(self):
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.zoom = 1
        self.map_min_x = 0.0
        self.map_max_x = 2000.0
        self.map_min_y = 0.0
        self.map_max_y = 1100.0

    def effective_hex_size(self):
        return HEX_SIZE if self.zoom == 1 else int(HEX_SIZE * 0.6)

    def pan(self, dx, dy):
        self.offset_x += dx
        self.offset_y += dy
        self._clamp()

    def _clamp(self):
        margin = 80
        visible_h = SCREEN_H - HUD_HEIGHT
        self.offset_x = max(SCREEN_W - self.map_max_x - margin,
                            min(margin - self.map_min_x, self.offset_x))
        self.offset_y = max(visible_h - self.map_max_y - margin,
                            min(margin - self.map_min_y, self.offset_y))

    def center_on_pixel(self, px, py):
        self.offset_x = SCREEN_W / 2 - px
        self.offset_y = (SCREEN_H - HUD_HEIGHT) / 2 - py
        self._clamp()


class Game:
    def __init__(self, num_players=4, map_cols=MAP_COLS, map_rows=MAP_ROWS, seed=None):
        self.num_players = num_players
        self.map_cols = map_cols
        self.map_rows = map_rows
        self.current_player = 0
        self.turn = 1
        self.winner = None  # player_index of domination winner

        self._rng = np.random.default_rng(
            None if seed is None else (seed ^ 0xABCD1234) & 0xFFFFFFFF
        )

        self.tiles = generate_map(map_cols, map_rows, seed=seed)
        self.civs = self._create_civs()
        self._place_starting_units()

        self.pending_messages: list[str] = []  # collected during end_turn

        self.camera = Camera()
        self._init_camera()

        # Center camera on player 1's first unit
        u = self.civs[0].units[0] if self.civs[0].units else None
        if u:
            px, py = hex_to_pixel(u.q, u.r, hex_size=HEX_SIZE)
            self.camera.center_on_pixel(px, py)

    # ------------------------------------------------------------------
    def _create_civs(self):
        civs = []
        for i in range(self.num_players):
            civs.append(Civilization(
                player_index=i,
                name=PLAYER_NAMES[i],
                color=PLAYER_COLORS[i],
            ))
        return civs

    def _find_start_tile(self, quadrant: int):
        """Find a grassland/plains tile in the given quadrant (0-3)."""
        half_r = self.map_rows // 2
        half_c = self.map_cols // 2

        candidates = []
        for (q, r), tile in self.tiles.items():
            col = q + (r - (r & 1)) // 2
            row = r
            in_top  = row < half_r
            in_left = col < half_c
            in_q = [
                in_top  and in_left,
                in_top  and not in_left,
                not in_top and in_left,
                not in_top and not in_left,
            ][quadrant]
            if not in_q:
                continue
            if tile.terrain in ("grassland", "plains"):
                candidates.append((q, r))

        if not candidates:
            # fallback: any passable tile in quadrant
            for (q, r), tile in self.tiles.items():
                col = q + (r - (r & 1)) // 2
                row = r
                in_top  = row < half_r
                in_left = col < half_c
                in_q = [
                    in_top  and in_left,
                    in_top  and not in_left,
                    not in_top and in_left,
                    not in_top and not in_left,
                ][quadrant]
                if in_q and TERRAIN_PASSABLE[tile.terrain]:
                    candidates.append((q, r))

        if not candidates:
            return None

        idx = int(self._rng.integers(0, len(candidates)))
        return candidates[idx]

    def _place_unit(self, unit: Unit):
        tile = self.tiles.get((unit.q, unit.r))
        if tile:
            if unit.is_civilian:
                tile.civilian = unit
            else:
                tile.unit = unit

    def _place_starting_units(self):
        from civ_game.map.hex_grid import hex_neighbors
        for i, civ in enumerate(self.civs):
            pos = self._find_start_tile(i)
            if not pos:
                continue
            q, r = pos
            settler = Unit("settler", i, q, r,
                           hp=UNIT_DEFS["settler"]["hp_max"],
                           moves_left=UNIT_DEFS["settler"]["moves"])
            worker = Unit("worker", i, q, r,
                          hp=UNIT_DEFS["worker"]["hp_max"],
                          moves_left=UNIT_DEFS["worker"]["moves"])
            warrior = Unit("warrior", i, q, r,
                           hp=UNIT_DEFS["warrior"]["hp_max"],
                           moves_left=UNIT_DEFS["warrior"]["moves"])

            # Spread out civilians to adjacent tiles
            placed_civilians = [(q, r)]  # settler takes start tile
            for nq, nr in hex_neighbors(q, r):
                t = self.tiles.get((nq, nr))
                if t and TERRAIN_PASSABLE[t.terrain] and (nq, nr) not in placed_civilians:
                    worker.q, worker.r = nq, nr
                    placed_civilians.append((nq, nr))
                    break

            # Place warrior on another adjacent tile (not on a civilian)
            for nq, nr in hex_neighbors(q, r):
                t = self.tiles.get((nq, nr))
                if (t and TERRAIN_PASSABLE[t.terrain]
                        and (nq, nr) not in placed_civilians
                        and t.unit is None):
                    warrior.q, warrior.r = nq, nr
                    break

            civ.units = [settler, worker, warrior]
            self._place_unit(settler)
            self._place_unit(worker)
            self._place_unit(warrior)

    def _init_camera(self):
        xs, ys = [], []
        hs = HEX_SIZE
        for (q, r) in self.tiles:
            px, py = hex_to_pixel(q, r, hex_size=hs)
            xs.append(px); ys.append(py)
        if not xs:
            return
        self.camera.map_min_x = min(xs) - hs
        self.camera.map_max_x = max(xs) + hs
        self.camera.map_min_y = min(ys) - hs
        self.camera.map_max_y = max(ys) + hs
        self.camera.center_on_pixel(
            (self.camera.map_min_x + self.camera.map_max_x) / 2,
            (self.camera.map_min_y + self.camera.map_max_y) / 2,
        )

    # ------------------------------------------------------------------
    def current_civ(self):
        return self.civs[self.current_player]

    # ------------------------------------------------------------------
    def move_unit(self, unit: Unit, q: int, r: int, cost: int = 1):
        """Move unit to (q, r), spending `cost` move points."""
        old_tile = self.tiles.get((unit.q, unit.r))
        if old_tile:
            if unit.is_civilian:
                old_tile.civilian = None
            else:
                old_tile.unit = None

        unit.q, unit.r = q, r
        unit.moves_left = max(0, unit.moves_left - cost)
        unit.fortified = False
        unit.fortify_bonus = 0.0
        unit.healing = False
        unit.building_improvement = None
        unit.build_turns_left = 0

        new_tile = self.tiles.get((q, r))
        if new_tile:
            if unit.is_civilian:
                new_tile.civilian = unit
            else:
                # If an enemy civilian is on the destination tile, capture it
                # (settlers are protected from capture on turn 1)
                if new_tile.civilian and new_tile.civilian.owner != unit.owner:
                    if not (self.turn <= 1 and new_tile.civilian.unit_type == "settler"):
                        self.remove_unit(new_tile.civilian)
                new_tile.unit = unit

    def found_city(self, unit: Unit):
        """Settler founds a city at its current position."""
        civ = self.civs[unit.owner]
        city_idx = len(civ.cities)
        name = CITY_NAMES[unit.owner][city_idx % len(CITY_NAMES[unit.owner])]

        city = City(
            name=name, q=unit.q, r=unit.r,
            owner=unit.owner,
            is_original_capital=(city_idx == 0),
        )

        # Claim tiles within radius 1
        for hq, hr in hexes_in_range(unit.q, unit.r, 1):
            tile = self.tiles.get((hq, hr))
            if tile and tile.terrain != "ocean" and tile.owner is None:
                tile.owner = unit.owner

        # Remove settler from tile and civ
        tile = self.tiles.get((unit.q, unit.r))
        if tile:
            tile.city = city
            tile.owner = unit.owner
            tile.civilian = None

        civ.units.remove(unit)
        civ.cities.append(city)
        if city.is_original_capital:
            civ.original_capital = city
            city.buildings.append("palace")

        auto_assign_worked_tiles(city, self.tiles)
        return city

    def upgrade_unit(self, unit) -> tuple[bool, str]:
        from civ_game.data.units import UNIT_DEFS, UNIT_UPGRADES
        if unit.is_civilian:
            return False, ""
        if unit.moves_left == 0:
            return False, "No moves left to upgrade."
        civ = self.civs[unit.owner]
        path = UNIT_UPGRADES.get(unit.unit_type)
        if not path:
            return False, f"{UNIT_DEFS[unit.unit_type]['name']} has no upgrade."
        target_type, gold_cost = path
        tdef = UNIT_DEFS[target_type]
        req_tech = tdef.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            return False, f"Requires {req_tech} technology."
        req_res = tdef.get("requires_resource")
        if req_res and not any(t.resource == req_res and t.owner == unit.owner
                               for t in self.tiles.values()):
            return False, f"Requires {req_res} resource."
        if civ.gold < gold_cost:
            return False, f"Need {gold_cost}g to upgrade (have {civ.gold}g)."
        # Apply upgrade
        civ.gold -= gold_cost
        old_def = UNIT_DEFS[unit.unit_type]
        hp_ratio = unit.hp / old_def["hp_max"]
        unit.unit_type  = target_type
        unit.hp         = max(1, round(hp_ratio * tdef["hp_max"]))
        unit.moves_left = 0
        unit.fortified  = False
        unit.fortify_bonus = 0.0
        unit.healing    = False
        return True, f"Upgraded to {tdef['name']} for {gold_cost}g!"

    def buy_item(self, city, item_key: str) -> tuple[bool, str]:
        from civ_game.data.units import UNIT_DEFS
        from civ_game.data.buildings import BUILDING_DEFS
        from civ_game.systems.production import get_item_cost, complete_item

        civ = self.civs[city.owner]

        # Already built?
        if item_key in BUILDING_DEFS and item_key in city.buildings:
            return False, f"{BUILDING_DEFS[item_key]['name']} already built."

        # Tech requirement
        defn = BUILDING_DEFS.get(item_key) or UNIT_DEFS.get(item_key)
        req_tech = defn.get("requires_tech") if defn else None
        if req_tech and req_tech not in civ.techs_researched:
            return False, f"Requires {req_tech} technology."

        # Resource requirement (units only)
        if item_key in UNIT_DEFS:
            req_res = UNIT_DEFS[item_key].get("requires_resource")
            if req_res and not any(
                t.resource == req_res and t.owner == city.owner
                for t in self.tiles.values()
            ):
                return False, f"Requires {req_res} resource."

        gold_cost = get_item_cost(item_key) * 2
        if civ.gold < gold_cost:
            return False, f"Need {gold_cost}g (have {civ.gold}g)."

        civ.gold -= gold_cost
        msg = complete_item(city, civ, self, item_key)
        return True, msg

    def start_improvement(self, unit: Unit, improvement_key: str):
        """Worker begins building an improvement."""
        from civ_game.entities.improvement import IMPROVEMENT_DEFS
        defn = IMPROVEMENT_DEFS[improvement_key]
        tile = self.tiles.get((unit.q, unit.r))
        if not tile or tile.terrain not in defn["valid_terrain"]:
            return False
        # Check tech requirement
        civ = self.civs[unit.owner]
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            return False
        unit.building_improvement = improvement_key
        unit.build_turns_left = defn["build_turns"]
        unit.moves_left = 0
        return True

    # ------------------------------------------------------------------
    def remove_unit(self, unit: Unit):
        """Remove a unit from the map and its civ's unit list."""
        tile = self.tiles.get((unit.q, unit.r))
        if tile:
            if unit.is_civilian and tile.civilian is unit:
                tile.civilian = None
            elif not unit.is_civilian and tile.unit is unit:
                tile.unit = None
        civ = self.civs[unit.owner]
        if unit in civ.units:
            civ.units.remove(unit)

    def _advance_unit(self, unit: Unit, tq: int, tr: int):
        """Move unit to (tq, tr) after combat — no moves cost."""
        old_tile = self.tiles.get((unit.q, unit.r))
        if old_tile and old_tile.unit is unit:
            old_tile.unit = None
        unit.q, unit.r = tq, tr
        new_tile = self.tiles.get((tq, tr))
        if new_tile:
            new_tile.unit = unit

    def _capture_city(self, attacker: Unit, city):
        """Transfer city ownership to attacker's civ and move attacker in."""
        old_owner_idx = city.owner
        new_owner_idx = attacker.owner

        # Move attacker into city tile
        old_tile = self.tiles.get((attacker.q, attacker.r))
        if old_tile and old_tile.unit is attacker:
            old_tile.unit = None

        attacker.q, attacker.r = city.q, city.r
        attacker.moves_left = 0

        city_tile = self.tiles.get((city.q, city.r))
        if city_tile:
            city_tile.unit = attacker
            city_tile.owner = new_owner_idx

        # Transfer between civ city lists
        old_civ = self.civs[old_owner_idx]
        new_civ = self.civs[new_owner_idx]
        if city in old_civ.cities:
            old_civ.cities.remove(city)
        new_civ.cities.append(city)

        city.owner = new_owner_idx
        city.hp = 50  # reset HP on capture

        # Transfer all territory tiles that belonged to this city
        for hq, hr in hexes_in_range(city.q, city.r, 3):
            t = self.tiles.get((hq, hr))
            if t and t.owner == old_owner_idx:
                t.owner = new_owner_idx

        # Eliminate old civ if no cities remain
        if not old_civ.cities:
            old_civ.is_eliminated = True
            for unit in list(old_civ.units):
                self.remove_unit(unit)
            old_civ.units.clear()

    def do_attack(self, attacker: Unit, target_q: int, target_r: int) -> str:
        """
        Execute an attack from attacker to (target_q, target_r).
        Returns a human-readable result message.
        """
        from civ_game.systems.combat import melee_attack, ranged_attack, bombard_city
        from civ_game.data.units import UNIT_DEFS as _DEFS

        target_tile = self.tiles.get((target_q, target_r))
        if not target_tile:
            return ""

        # Settlers are protected from attack on turn 1
        if self.turn <= 1:
            target_unit_check = target_tile.unit or target_tile.civilian
            if target_unit_check and target_unit_check.unit_type == "settler":
                return ""

        attacker_tile = self.tiles.get((attacker.q, attacker.r))
        defn = _DEFS[attacker.unit_type]
        unit_type = defn["type"]

        # Consume all moves and cancel fortify/healing
        attacker.moves_left = 0
        attacker.fortified = False
        attacker.fortify_bonus = 0.0
        attacker.healing = False

        target_unit = target_tile.unit or target_tile.civilian
        target_city = target_tile.city
        msg = ""

        if target_unit and target_unit.owner != attacker.owner:
            # ---- Attack enemy unit ----
            if unit_type == "melee":
                a_dmg, d_dmg = melee_attack(attacker, target_unit,
                                             attacker_tile, target_tile)
                msg = (f"{defn['name']} vs {_DEFS[target_unit.unit_type]['name']}: "
                       f"-{a_dmg} / -{d_dmg} HP")
            else:
                d_dmg = ranged_attack(attacker, target_unit, target_tile)
                msg = f"Ranged hit: {_DEFS[target_unit.unit_type]['name']} -{d_dmg} HP"

            if target_unit.hp <= 0:
                self.remove_unit(target_unit)
                target_unit = None
                if unit_type == "melee" and attacker.hp > 0:
                    # Advance after combat (only if attacker survived)
                    if target_city and target_city.owner != attacker.owner:
                        old_owner_idx = target_city.owner
                        self._capture_city(attacker, target_city)
                        msg += f" → {target_city.name} captured!"
                        if self.civs[old_owner_idx].is_eliminated:
                            msg += f" {self.civs[old_owner_idx].name} eliminated!"
                    else:
                        self._advance_unit(attacker, target_q, target_r)

            if attacker.hp <= 0:
                self.remove_unit(attacker)
                msg += " (attacker died)"

        elif target_city and target_city.owner != attacker.owner and not target_unit:
            # ---- Attack undefended city ----
            if unit_type == "ranged":
                dmg = bombard_city(attacker, target_city)
                msg = (f"Bombarded {target_city.name}: -{dmg} HP "
                       f"(HP: {target_city.hp}/50)")
            elif unit_type == "melee":
                old_owner_idx = target_city.owner
                dmg = bombard_city(attacker, target_city)
                if target_city.hp <= 0:
                    self._capture_city(attacker, target_city)
                    msg = f"Captured {target_city.name}!"
                    if self.civs[old_owner_idx].is_eliminated:
                        msg += f" {self.civs[old_owner_idx].name} eliminated!"
                else:
                    msg = (f"Attacked {target_city.name}: -{dmg} HP "
                           f"(HP: {target_city.hp}/50)")

        self.check_victory()
        return msg

    def check_victory(self):
        """Check if any player owns all original capitals."""
        if self.winner is not None:
            return
        if self.turn <= 1:
            return  # no victory possible before everyone has had a chance to settle
        original_caps = [c.original_capital for c in self.civs
                         if c.original_capital is not None]
        if not original_caps:
            return
        for civ in self.civs:
            if all(cap.owner == civ.player_index for cap in original_caps):
                self.winner = civ.player_index
                return

    # ------------------------------------------------------------------
    def _expand_border(self, civ):
        """Claim one unclaimed tile adjacent to this civ's territory (best yield first)."""
        from civ_game.map.hex_grid import hex_neighbors

        candidates = set()
        for (q, r), tile in self.tiles.items():
            if tile.owner != civ.player_index:
                continue
            for nq, nr in hex_neighbors(q, r):
                nb = self.tiles.get((nq, nr))
                if nb and nb.owner is None and nb.terrain != "ocean":
                    candidates.add((nq, nr))

        if not candidates:
            return

        def score(pos):
            t = self.tiles[pos]
            y = TERRAIN_YIELDS[t.terrain]
            total = y["food"] + y["prod"] + y["gold"]
            if t.resource:
                r = RESOURCES[t.resource]["yield_bonus"]
                total += r.get("food", 0) + r.get("prod", 0) + r.get("gold", 0)
            return total

        best = max(candidates, key=score)
        self.tiles[best].owner = civ.player_index

    def _apply_bankruptcy(self, civ):
        """Civ ran out of gold: lose a random military unit or non-palace building."""
        import random
        from civ_game.data.buildings import BUILDING_DEFS

        # Build pool of losable things
        losable = []

        for unit in civ.units:
            if not unit.is_civilian:
                losable.append(("unit", unit, None))

        for city in civ.cities:
            for b_key in city.buildings:
                if b_key != "palace":
                    losable.append(("building", b_key, city))

        civ.gold = 0

        if not losable:
            civ.pending_messages.append("Bankruptcy! No gold left.")
            return

        kind, obj, city = random.choice(losable)
        if kind == "unit":
            from civ_game.data.units import UNIT_DEFS as _UD
            name = _UD[obj.unit_type]["name"]
            self.remove_unit(obj)
            civ.pending_messages.append(
                f"Bankruptcy! {name} disbanded — treasury emptied.")
        else:
            from civ_game.data.buildings import BUILDING_DEFS as _BD
            name = _BD[obj]["name"]
            city.buildings.remove(obj)
            civ.pending_messages.append(
                f"Bankruptcy! {name} in {city.name} lost — treasury emptied.")

    def end_turn(self):
        civ = self.current_civ()

        # Process each city
        for city in civ.cities:
            yields = compute_city_yields(city, self.tiles, civ)

            # Food growth
            net_food = yields["food"] - city.population * 2
            city.food_stored = max(0, city.food_stored + net_food)
            if city.food_stored >= city.food_growth_threshold:
                city.population += 1
                city.food_stored = 0
                auto_assign_worked_tiles(city, self.tiles)

            # Gold (includes building maintenance subtracted in yields) + science
            civ.gold += yields["gold"]
            civ.science += yields["science"]

            # Culture → border expansion (1 tile per 20 culture)
            civ.culture += yields["culture"]
            city.culture_stored += yields["culture"]
            while city.culture_stored >= 20:
                city.culture_stored -= 20
                self._expand_border(civ)

            # City HP regeneration
            if city.hp < 50:
                city.hp = min(50, city.hp + 5)

        # Unit maintenance: 1 gold per military unit per turn
        for unit in civ.units:
            if not unit.is_civilian:
                civ.gold -= 1

        # Research progress
        if civ.current_research:
            from civ_game.data.techs import TECH_DEFS
            tech_cost = TECH_DEFS[civ.current_research]["science_cost"]
            if civ.science >= tech_cost:
                civ.science -= tech_cost
                tech_name = TECH_DEFS[civ.current_research]["name"]
                civ.techs_researched.add(civ.current_research)
                civ.current_research = None
                civ.pending_messages.append(f"{tech_name} researched!")
                civ.research_just_completed = True

        # Worker improvement build progress
        for unit in list(civ.units):
            if unit.building_improvement and unit.build_turns_left > 0:
                unit.build_turns_left -= 1
                if unit.build_turns_left == 0:
                    tile = self.tiles.get((unit.q, unit.r))
                    if tile:
                        tile.improvement = unit.building_improvement
                    unit.building_improvement = None

        # Production (separate loop to avoid double-processing new units)
        from civ_game.systems.production import process_production
        for city in civ.cities:
            msg = process_production(city, civ, self)
            if msg:
                civ.pending_messages.append(msg)

        # Reset unit movement, handle fortification and healing
        for unit in civ.units:
            if unit.healing:
                hp_max = UNIT_DEFS[unit.unit_type]["hp_max"]
                tile = self.tiles.get((unit.q, unit.r))
                in_own_territory = tile and tile.owner == civ.player_index
                unit.hp = min(hp_max, unit.hp + (20 if in_own_territory else 10))
            unit.moves_left = UNIT_DEFS[unit.unit_type]["moves"]
            if unit.fortified:
                unit.fortify_bonus = min(0.5, unit.fortify_bonus + 0.25)

        # Bankruptcy: negative gold → lose a random military unit or building
        if civ.gold < 0:
            self._apply_bankruptcy(civ)

        # Advance to next non-eliminated player, incrementing turn on wrap-around
        for _ in range(self.num_players):
            next_player = (self.current_player + 1) % self.num_players
            if next_player == 0:
                self.turn += 1
            self.current_player = next_player
            if not self.civs[self.current_player].is_eliminated:
                break
