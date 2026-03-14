import numpy as np
from civ_game.map.hex_grid import HEX_SIZE, hex_to_pixel, hexes_in_range
from civ_game.map.generator import generate_map
from civ_game.map.terrain import TERRAIN_PASSABLE
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

PLAYER_NAMES = ["Player 1", "Player 2", "Player 3", "Player 4"]
PLAYER_COLORS = [
    (220, 50,  50),
    (50,  100, 220),
    (50,  180, 50),
    (220, 180, 50),
]

CITY_NAMES = [
    ["Rome",    "Florence", "Venice",  "Genoa",   "Naples"],
    ["Athens",  "Sparta",   "Corinth", "Thebes",  "Argos"],
    ["Delhi",   "Agra",     "Patna",   "Mysore",  "Lahore"],
    ["Babylon", "Ur",       "Nineveh", "Kish",    "Akkad"],
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

        self._rng = np.random.default_rng(
            None if seed is None else (seed ^ 0xABCD1234) & 0xFFFFFFFF
        )

        self.tiles = generate_map(map_cols, map_rows, seed=seed)
        self.civs = self._create_civs()
        self._place_starting_units()

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
            # Place worker one tile away if possible
            from civ_game.map.hex_grid import hex_neighbors
            for nq, nr in hex_neighbors(q, r):
                t = self.tiles.get((nq, nr))
                if t and TERRAIN_PASSABLE[t.terrain] and t.civilian is None:
                    worker.q, worker.r = nq, nr
                    break

            civ.units = [settler, worker]
            self._place_unit(settler)
            self._place_unit(worker)

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
    def move_unit(self, unit: Unit, q: int, r: int):
        """Move unit to (q, r), updating tile references."""
        old_tile = self.tiles.get((unit.q, unit.r))
        if old_tile:
            if unit.is_civilian:
                old_tile.civilian = None
            else:
                old_tile.unit = None

        unit.q, unit.r = q, r
        unit.moves_left = max(0, unit.moves_left - 1)
        unit.fortified = False
        unit.fortify_bonus = 0.0
        unit.building_improvement = None
        unit.build_turns_left = 0

        new_tile = self.tiles.get((q, r))
        if new_tile:
            if unit.is_civilian:
                new_tile.civilian = unit
            else:
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

    def start_improvement(self, unit: Unit, improvement_key: str):
        """Worker begins building an improvement."""
        from civ_game.entities.improvement import IMPROVEMENT_DEFS
        defn = IMPROVEMENT_DEFS[improvement_key]
        tile = self.tiles.get((unit.q, unit.r))
        if not tile or tile.terrain not in defn["valid_terrain"]:
            return False
        unit.building_improvement = improvement_key
        unit.build_turns_left = defn["build_turns"]
        unit.moves_left = 0
        return True

    # ------------------------------------------------------------------
    def _expand_border(self, civ):
        """Claim one unclaimed tile adjacent to this civ's territory (best yield first)."""
        from civ_game.map.hex_grid import hex_neighbors
        from civ_game.map.terrain import TERRAIN_YIELDS

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
            y = TERRAIN_YIELDS[self.tiles[pos].terrain]
            return y["food"] + y["prod"] + y["gold"]

        best = max(candidates, key=score)
        self.tiles[best].owner = civ.player_index

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

            # Gold + science
            civ.gold += yields["gold"]
            civ.science += yields["science"]

            # Culture → border expansion (1 tile per 20 culture)
            civ.culture += yields["culture"]
            city.culture_stored += yields["culture"]
            while city.culture_stored >= 20:
                city.culture_stored -= 20
                self._expand_border(civ)

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
            process_production(city, civ, self)

        # Reset unit movement
        for unit in civ.units:
            unit.moves_left = UNIT_DEFS[unit.unit_type]["moves"]

        # Advance turn
        self.current_player = (self.current_player + 1) % self.num_players
        if self.current_player == 0:
            self.turn += 1
