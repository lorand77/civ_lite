import pygame
from dataclasses import dataclass, field

SCREEN_W = 1280
SCREEN_H = 720
HUD_HEIGHT = 120

COLOR_HUD_BG = (30, 30, 30)
COLOR_TEXT   = (255, 255, 255)
COLOR_TEXT_DIM = (180, 180, 180)
COLOR_BTN_BG = (60, 100, 60)
COLOR_BTN_HOVER = (80, 140, 80)
COLOR_BTN_TEXT = (255, 255, 255)

PLAYER_NAMES  = ["Player 1", "Player 2", "Player 3", "Player 4"]
PLAYER_COLORS = [
    (220, 50,  50),
    (50,  100, 220),
    (50,  180, 50),
    (220, 180, 50),
]

END_TURN_RECT = pygame.Rect(SCREEN_W - 160, SCREEN_H - 50, 140, 34)


@dataclass
class UIState:
    selected_tile: object = None
    pan_start: tuple | None = None

    # Placeholders for future phases
    selected_unit: object = None
    selected_city: object = None
    reachable_tiles: set = field(default_factory=set)
    city_screen_open: bool = False
    tech_screen_open: bool = False
    turn_banner_timer: int = 0

    def deselect(self):
        self.selected_tile = None
        self.selected_unit = None


_font_cache: dict[int, pygame.font.Font] = {}

def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def render_hud(screen, game, ui_state):
    # Background bar
    hud_rect = pygame.Rect(0, SCREEN_H - HUD_HEIGHT, SCREEN_W, HUD_HEIGHT)
    pygame.draw.rect(screen, COLOR_HUD_BG, hud_rect)
    pygame.draw.line(screen, (80, 80, 80), (0, SCREEN_H - HUD_HEIGHT),
                     (SCREEN_W, SCREEN_H - HUD_HEIGHT), 1)

    # Divider between left and right panels
    divider_x = SCREEN_W // 2
    pygame.draw.line(screen, (70, 70, 70),
                     (divider_x, SCREEN_H - HUD_HEIGHT + 10),
                     (divider_x, SCREEN_H - 10), 1)

    base_y = SCREEN_H - HUD_HEIGHT + 12
    lx = 20   # left column x
    rx = divider_x + 20  # right column x
    line_h = 22

    f_large  = _font(15)
    f_normal = _font(13)
    f_small  = _font(11)

    # --- Left panel: selected tile info ---
    tile = ui_state.selected_tile
    if tile is None:
        text = f_normal.render("Click a tile to select it", True, COLOR_TEXT_DIM)
        screen.blit(text, (lx, base_y + line_h))
    else:
        from civ_game.map.terrain import TERRAIN_YIELDS, RESOURCES, TERRAIN_COLORS

        # Terrain name
        terrain_label = tile.terrain.capitalize()
        color = TERRAIN_COLORS.get(tile.terrain, COLOR_TEXT)
        heading = f_large.render(f"Terrain: {terrain_label}", True, color)
        screen.blit(heading, (lx, base_y))

        # Resource
        if tile.resource:
            from civ_game.map.terrain import RESOURCE_COLORS, RESOURCES
            res_color = RESOURCE_COLORS.get(tile.resource, COLOR_TEXT)
            res_info = RESOURCES[tile.resource]
            bonus_parts = [f"+{v} {k}" for k, v in res_info["yield_bonus"].items()]
            bonus_str = ", ".join(bonus_parts)
            res_text = f_normal.render(
                f"Resource: {tile.resource.capitalize()}  ({bonus_str})",
                True, res_color
            )
            screen.blit(res_text, (lx, base_y + line_h))
        else:
            no_res = f_normal.render("Resource: None", True, COLOR_TEXT_DIM)
            screen.blit(no_res, (lx, base_y + line_h))

        # Yields
        yields = TERRAIN_YIELDS.get(tile.terrain, {})
        food = yields.get("food", 0)
        prod = yields.get("prod", 0)
        gold = yields.get("gold", 0)

        # Add resource bonus to yields
        if tile.resource:
            res_yields = RESOURCES[tile.resource]["yield_bonus"]
            food += res_yields.get("food", 0)
            prod += res_yields.get("prod", 0)
            gold += res_yields.get("gold", 0)

        yields_text = f_normal.render(
            f"Yields:  Food {food}   Prod {prod}   Gold {gold}",
            True, COLOR_TEXT
        )
        screen.blit(yields_text, (lx, base_y + line_h * 2))

        # Coords
        coord_text = f_small.render(f"Hex: ({tile.q}, {tile.r})", True, COLOR_TEXT_DIM)
        screen.blit(coord_text, (lx, base_y + line_h * 3))

    # --- Right panel: turn / player info ---
    player_idx = game.current_player
    player_name = PLAYER_NAMES[player_idx]
    player_color = PLAYER_COLORS[player_idx]

    turn_text = f_large.render(f"Turn {game.turn}", True, COLOR_TEXT)
    screen.blit(turn_text, (rx, base_y))

    player_text = f_normal.render(player_name, True, player_color)
    screen.blit(player_text, (rx, base_y + line_h))

    zoom_label = "Normal" if game.camera.zoom == 1 else "Zoomed Out"
    zoom_text = f_small.render(f"Zoom: {zoom_label}  |  Scroll to zoom, Arrows/MMB to pan",
                               True, COLOR_TEXT_DIM)
    screen.blit(zoom_text, (rx, base_y + line_h * 2))

    # --- END TURN button ---
    mouse_pos = pygame.mouse.get_pos()
    btn_color = COLOR_BTN_HOVER if END_TURN_RECT.collidepoint(mouse_pos) else COLOR_BTN_BG
    pygame.draw.rect(screen, btn_color, END_TURN_RECT, border_radius=4)
    pygame.draw.rect(screen, (100, 160, 100), END_TURN_RECT, 1, border_radius=4)
    btn_font = _font(14)
    btn_surf = btn_font.render("END TURN", True, COLOR_BTN_TEXT)
    btn_rect = btn_surf.get_rect(center=END_TURN_RECT.center)
    screen.blit(btn_surf, btn_rect)
