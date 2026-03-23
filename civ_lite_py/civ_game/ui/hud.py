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
    screen: object = None          # pygame surface, set once in main()
    selected_tile: object = None
    pan_start: tuple | None = None

    selected_unit: object = None
    selected_city: object = None
    reachable_tiles: dict = field(default_factory=dict)
    attackable_tiles: set = field(default_factory=set)

    city_screen_open: bool = False
    city_screen_item_rects: list = field(default_factory=list)
    city_screen_buy_rects: list = field(default_factory=list)
    city_screen_close_rect: object = None
    city_screen_scroll: int = 0

    tech_screen_open: bool = False
    turn_banner_timer: int = 0

    message: str = ""
    message_timer: int = 0
    queued_message: str = ""   # shown after turn banner clears
    auto_open_tech: bool = False  # open tech screen after banner clears

    score_history: list = field(default_factory=list)  # [[s0,s1,s2,s3], ...] per game turn
    _last_recorded_turn: int = 0
    paused: bool = False

    def set_message(self, msg: str, duration: int = 180):
        self.message = msg
        self.message_timer = duration

    def deselect(self):
        self.selected_tile = None
        self.selected_unit = None
        self.selected_city = None
        self.reachable_tiles = {}
        self.attackable_tiles = set()


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

    # Science with cost context
    if civ.current_research:
        from civ_game.data.techs import TECH_DEFS
        tech_cost = TECH_DEFS[civ.current_research]["science_cost"]
        sci_str = (f"Gold: {civ.gold}   Sci: {civ.science}/{tech_cost}"
                   f"   {TECH_DEFS[civ.current_research]['name']}")
        sci_color = (120, 200, 255)
    else:
        sci_str = (f"Gold: {civ.gold}   Science: {civ.science}   Cities: {len(civ.cities)}"
                   f"   [T=Research]")
        sci_color = COLOR_TEXT_DIM
    screen.blit(_font(20).render(sci_str, True, sci_color), (rx, base_y + lh * 2))

    screen.blit(_font(20).render(
        "Arrows/MMB=pan  F=found  B=city  M/A/P=improve  K=fortify  H=heal  T=tech  Enter=end",
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
    from civ_game.data.civs import is_special_unit, CIV_TRAITS, get_unit_move_bonus
    defn = UNIT_DEFS[unit.unit_type]
    civ_color = PLAYER_COLORS[unit.owner]

    special_mark = " \u2605" if is_special_unit(unit.owner, unit.unit_type) else ""
    status = "  [FORTIFIED]" if unit.fortified else ("  [HEALING]" if unit.healing else "")
    screen.blit(_font(23).render(f"{defn['name']}{special_mark}  HP {unit.hp}/{defn['hp_max']}{status}",
                                 True, civ_color), (lx, base_y))

    # Compute display strength with civ bonuses
    traits = CIV_TRAITS.get(unit.owner, {})
    su = traits.get("special_units", {}).get(unit.unit_type, {})
    str_mult = (1 + su.get("strength_bonus", 0.0)) * (1 + traits.get("all_units_strength_bonus", 0.0))
    str_val = round(defn['strength'] * str_mult, 1)
    rstr = defn.get('ranged_strength')
    rng  = defn.get('range')
    if rstr:
        rstr_display = round(rstr * str_mult, 1)
        str_info = f"Str: {str_val}  Ranged: {rstr_display}  Range: {rng}"
    else:
        str_info = f"Str: {str_val}"
    base_moves = defn['moves'] + get_unit_move_bonus(unit.owner, unit.unit_type)
    screen.blit(_font(20).render(
        f"Moves: {unit.moves_left}/{base_moves}   {str_info}",
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
        civ = game.civs[unit.owner]
        hints = []
        if tile:
            if tile.terrain in ("grassland", "plains"):
                hints.append("A=Farm")
                if "animal_husbandry" in civ.techs_researched:
                    hints.append("P=Pasture")
            if tile.terrain in ("hills", "forest"):
                if "mining" in civ.techs_researched:
                    hints.append("M=Mine")
        screen.blit(_font(20).render("Build:  " + "  ".join(hints) if hints else "No improvements available",
                                     True, COLOR_TEXT_DIM), (lx, base_y + lh * 2))
    elif defn["type"] in ("melee", "ranged"):
        from civ_game.data.units import UNIT_UPGRADES, UNIT_DEFS
        tile = game.tiles.get((unit.q, unit.r))
        in_own = tile and tile.owner == unit.owner
        hp_rate = 20 if in_own else 10

        upg_hint = ""
        path = UNIT_UPGRADES.get(unit.unit_type)
        if path and unit.moves_left > 0:
            target_type, gold_cost = path
            tdef = UNIT_DEFS[target_type]
            civ = game.civs[unit.owner]
            req_tech = tdef.get("requires_tech")
            req_res  = tdef.get("requires_resource")
            tech_ok  = not req_tech or req_tech in civ.techs_researched
            res_ok   = not req_res or any(
                t.resource == req_res and t.owner == unit.owner
                for t in game.tiles.values()
            )
            gold_ok  = civ.gold >= gold_cost
            if tech_ok and res_ok and gold_ok:
                upg_hint = f"  U=Upgrade->{tdef['name']}({gold_cost}g)"

        hint = f"Click red=attack  K=fortify  H=heal (+{hp_rate} HP/turn){upg_hint}"
        screen.blit(_font(20).render(hint, True, (255, 160, 80)),
                    (lx, base_y + lh * 2))

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
