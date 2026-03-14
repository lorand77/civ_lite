import pygame
from dataclasses import dataclass, field

SCREEN_W = 1850
SCREEN_H = 1000
HUD_HEIGHT = 180

COLOR_HUD_BG   = (30, 30, 30)
COLOR_TEXT     = (255, 255, 255)
COLOR_TEXT_DIM = (160, 160, 160)
COLOR_BTN_BG   = (60, 100, 60)
COLOR_BTN_HOV  = (80, 140, 80)

PLAYER_NAMES  = ["Player 1", "Player 2", "Player 3", "Player 4"]
PLAYER_COLORS = [
    (220, 50,  50),
    (50,  100, 220),
    (50,  180, 50),
    (220, 180, 50),
]

END_TURN_RECT = pygame.Rect(SCREEN_W - 220, SCREEN_H - 66, 200, 48)


@dataclass
class UIState:
    selected_tile: object = None
    pan_start: tuple | None = None

    selected_unit: object = None
    selected_city: object = None
    reachable_tiles: set = field(default_factory=set)

    city_screen_open: bool = False
    city_screen_item_rects: list = field(default_factory=list)
    city_screen_close_rect: object = None

    tech_screen_open: bool = False
    turn_banner_timer: int = 0

    def deselect(self):
        self.selected_tile = None
        self.selected_unit = None
        self.selected_city = None
        self.reachable_tiles = set()


_font_cache: dict[int, pygame.font.Font] = {}

def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def render_hud(screen, game, ui_state):
    hud_rect = pygame.Rect(0, SCREEN_H - HUD_HEIGHT, SCREEN_W, HUD_HEIGHT)
    pygame.draw.rect(screen, COLOR_HUD_BG, hud_rect)
    pygame.draw.line(screen, (80, 80, 80),
                     (0, SCREEN_H - HUD_HEIGHT), (SCREEN_W, SCREEN_H - HUD_HEIGHT), 1)

    divider_x = SCREEN_W // 2
    pygame.draw.line(screen, (70, 70, 70),
                     (divider_x, SCREEN_H - HUD_HEIGHT + 10),
                     (divider_x, SCREEN_H - 10), 1)

    base_y = SCREEN_H - HUD_HEIGHT + 10
    lx = 20
    rx = divider_x + 20
    lh = 32

    # ---- Left panel ----
    unit = ui_state.selected_unit
    city = ui_state.selected_city
    tile = ui_state.selected_tile

    if unit:
        _draw_unit_info(screen, unit, game, lx, base_y, lh)
    elif city:
        _draw_city_info(screen, city, game, lx, base_y, lh)
    elif tile:
        _draw_tile_info(screen, tile, lx, base_y, lh)
    else:
        screen.blit(_font(20).render("Click a unit, city, or tile", True, COLOR_TEXT_DIM),
                    (lx, base_y + lh))

    # ---- Right panel ----
    civ = game.current_civ()
    screen.blit(_font(23).render(f"Turn {game.turn}", True, COLOR_TEXT),
                (rx, base_y))
    screen.blit(_font(20).render(civ.name, True, PLAYER_COLORS[civ.player_index]),
                (rx, base_y + lh))
    screen.blit(_font(20).render(
        f"Gold: {civ.gold}   Science: {civ.science}   Cities: {len(civ.cities)}",
        True, COLOR_TEXT_DIM), (rx, base_y + lh * 2))
    screen.blit(_font(20).render(
        "Arrows/MMB=pan  Scroll=zoom  F=found  B=city  M/A/P=improve  Enter=end turn",
        True, COLOR_TEXT_DIM), (rx, base_y + lh * 3))

    # END TURN button
    mp = pygame.mouse.get_pos()
    bc = COLOR_BTN_HOV if END_TURN_RECT.collidepoint(mp) else COLOR_BTN_BG
    pygame.draw.rect(screen, bc, END_TURN_RECT, border_radius=6)
    pygame.draw.rect(screen, (100, 160, 100), END_TURN_RECT, 1, border_radius=6)
    btn = _font(21).render("END TURN", True, COLOR_TEXT)
    screen.blit(btn, btn.get_rect(center=END_TURN_RECT.center))


def _draw_unit_info(screen, unit, game, lx, base_y, lh):
    from civ_game.data.units import UNIT_DEFS
    from civ_game.entities.improvement import IMPROVEMENT_DEFS
    defn = UNIT_DEFS[unit.unit_type]
    civ_color = PLAYER_COLORS[unit.owner]

    screen.blit(_font(23).render(f"{defn['name']}  (HP {unit.hp}/{defn['hp_max']})",
                                 True, civ_color), (lx, base_y))
    screen.blit(_font(20).render(
        f"Moves: {unit.moves_left}/{defn['moves']}   Strength: {defn['strength']}",
        True, COLOR_TEXT), (lx, base_y + lh))

    if unit.building_improvement:
        imp = IMPROVEMENT_DEFS[unit.building_improvement]
        screen.blit(_font(20).render(
            f"Building {imp['name']}  ({unit.build_turns_left} turns left)",
            True, (255, 220, 80)), (lx, base_y + lh * 2))
    elif unit.unit_type == "settler":
        screen.blit(_font(20).render("F = Found City", True, COLOR_TEXT_DIM),
                    (lx, base_y + lh * 2))
    elif unit.unit_type == "worker":
        tile = game.tiles.get((unit.q, unit.r))
        hints = []
        if tile:
            if tile.terrain in ("grassland", "plains"):
                hints += ["A=Farm", "P=Pasture"]
            if tile.terrain == "hills":
                hints.append("M=Mine")
        screen.blit(_font(20).render("Build:  " + "  ".join(hints) if hints else "No improvements here",
                                     True, COLOR_TEXT_DIM), (lx, base_y + lh * 2))

    # HP bar
    _draw_hp_bar(screen, lx, base_y + lh * 3 + 4, unit.hp, defn["hp_max"], 160)


def _draw_city_info(screen, city, game, lx, base_y, lh):
    from civ_game.systems.yields import compute_city_yields
    civ = game.civs[city.owner]
    yields = compute_city_yields(city, game.tiles, civ)
    civ_color = PLAYER_COLORS[city.owner]

    screen.blit(_font(23).render(f"{city.name}  (Pop {city.population})",
                                 True, civ_color), (lx, base_y))
    screen.blit(_font(20).render(
        f"Food {city.food_stored}/{city.food_growth_threshold}  "
        f"F:{yields['food']} P:{yields['prod']} G:{yields['gold']}",
        True, COLOR_TEXT), (lx, base_y + lh))

    if city.production_queue:
        from civ_game.systems.production import get_item_cost
        from civ_game.data.buildings import BUILDING_DEFS
        from civ_game.data.units import UNIT_DEFS
        key = city.production_queue[0]
        name = (BUILDING_DEFS[key]["name"] if key in BUILDING_DEFS
                else UNIT_DEFS[key]["name"] if key in UNIT_DEFS else key)
        cost = get_item_cost(key)
        screen.blit(_font(20).render(
            f"Building: {name}  {city.production_progress}/{cost}",
            True, (180, 220, 180)), (lx, base_y + lh * 2))
    else:
        screen.blit(_font(20).render("Nothing in production queue", True, COLOR_TEXT_DIM),
                    (lx, base_y + lh * 2))

    screen.blit(_font(20).render("B = Open city screen", True, COLOR_TEXT_DIM),
                (lx, base_y + lh * 3))


def _draw_tile_info(screen, tile, lx, base_y, lh):
    from civ_game.map.terrain import TERRAIN_COLORS, TERRAIN_YIELDS, RESOURCES, RESOURCE_COLORS
    color = TERRAIN_COLORS.get(tile.terrain, COLOR_TEXT)
    screen.blit(_font(23).render(f"Terrain: {tile.terrain.capitalize()}", True, color),
                (lx, base_y))

    if tile.resource:
        res_color = RESOURCE_COLORS.get(tile.resource, COLOR_TEXT)
        res = RESOURCES[tile.resource]
        bonus = ", ".join(f"+{v} {k}" for k, v in res["yield_bonus"].items())
        screen.blit(_font(20).render(
            f"Resource: {tile.resource.capitalize()}  ({bonus})", True, res_color),
            (lx, base_y + lh))
    else:
        screen.blit(_font(20).render("Resource: None", True, COLOR_TEXT_DIM),
                    (lx, base_y + lh))

    y = TERRAIN_YIELDS.get(tile.terrain, {})
    f, p, g = y.get("food", 0), y.get("prod", 0), y.get("gold", 0)
    if tile.resource:
        rb = RESOURCES[tile.resource]["yield_bonus"]
        f += rb.get("food", 0); p += rb.get("prod", 0); g += rb.get("gold", 0)
    screen.blit(_font(20).render(f"Yields:  Food {f}   Prod {p}   Gold {g}",
                                 True, COLOR_TEXT), (lx, base_y + lh * 2))
    screen.blit(_font(20).render(f"Hex ({tile.q}, {tile.r})", True, COLOR_TEXT_DIM),
                (lx, base_y + lh * 3))


def _draw_hp_bar(screen, x, y, hp, max_hp, width=100):
    filled = int(width * hp / max_hp)
    pygame.draw.rect(screen, (80, 30, 30), (x, y, width, 8))
    pygame.draw.rect(screen, (200, 60, 60), (x, y, filled, 8))
    pygame.draw.rect(screen, (120, 120, 120), (x, y, width, 8), 1)
