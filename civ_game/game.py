import math
from dataclasses import dataclass, field
from civ_game.map.hex_grid import HEX_SIZE, hex_to_pixel, offset_to_axial
from civ_game.map.generator import generate_map

MAP_COLS = 32
MAP_ROWS = 20
SCREEN_W = 1280
SCREEN_H = 720
HUD_HEIGHT = 120
NUM_PLAYERS = 4


@dataclass
class Camera:
    offset_x: float = 0.0
    offset_y: float = 0.0
    zoom: int = 1  # 1 = normal, 0 = zoomed out

    # Map pixel bounds (set by Game after generation)
    map_min_x: float = 0.0
    map_max_x: float = 2000.0
    map_min_y: float = 0.0
    map_max_y: float = 1100.0

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
    def __init__(self, num_players=4, map_cols=MAP_COLS, map_rows=MAP_ROWS, seed=42):
        self.num_players = num_players
        self.map_cols = map_cols
        self.map_rows = map_rows
        self.current_player = 0
        self.turn = 1

        # Generate map
        self.tiles = generate_map(map_cols, map_rows, seed=seed)

        # Set up camera
        self.camera = Camera()
        self._init_camera()

    def _init_camera(self):
        """Compute map pixel bounds and center camera on the map."""
        xs = []
        ys = []
        hs = HEX_SIZE
        for (q, r) in self.tiles:
            px, py = hex_to_pixel(q, r, hex_size=hs)
            xs.append(px)
            ys.append(py)

        if not xs:
            return

        min_x = min(xs) - hs
        max_x = max(xs) + hs
        min_y = min(ys) - hs
        max_y = max(ys) + hs

        self.camera.map_min_x = min_x
        self.camera.map_max_x = max_x
        self.camera.map_min_y = min_y
        self.camera.map_max_y = max_y

        # Center camera on map center
        center_px = (min_x + max_x) / 2
        center_py = (min_y + max_y) / 2
        self.camera.center_on_pixel(center_px, center_py)

    def end_turn(self):
        self.current_player = (self.current_player + 1) % self.num_players
        if self.current_player == 0:
            self.turn += 1
