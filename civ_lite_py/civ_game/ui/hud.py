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
    stats_screen_open: bool = False

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
        "Arrows/MMB=pan  F=found  B=city  M/A/P=improve  K=fortify  H=heal  T=tech  S=stats  Enter=end",
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

    status = "  [FORTIFIED]" if unit.fortified else ("  [HEALING]" if unit.healing else "")
    screen.blit(_font(23).render(f"{defn['name']}  HP {unit.hp}/{defn['hp_max']}{status}",
                                 True, civ_color), (lx, base_y))

    str_val = defn['strength']
    rstr = defn.get('ranged_strength')
    rng  = defn.get('range')
    if rstr:
        str_info = f"Str: {str_val}  Ranged: {rstr}  Range: {rng}"
    else:
        str_info = f"Str: {str_val}"
    screen.blit(_font(20).render(
        f"Moves: {unit.moves_left}/{defn['moves']}   {str_info}",
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
            if tile.terrain in ("hills", "forest") or (
                tile.terrain in ("grassland", "plains") and tile.resource == "gold"
            ):
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


def render_stats_screen(screen, game):
    from civ_game.data.units import UNIT_DEFS
    from civ_game.systems.score import compute_score
    from civ_game.systems.yields import compute_city_yields

    WIN_W = 700
    WIN_H = 440
    WIN_X = (SCREEN_W - WIN_W) // 2
    WIN_Y = (SCREEN_H - WIN_H) // 2

    LABEL_W = 140
    CIV_COL_W = (WIN_W - LABEL_W) // 4
    ROW_H = 36
    HDR_H = 44

    bg = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
    bg.fill((20, 20, 30, 235))
    screen.blit(bg, (WIN_X, WIN_Y))
    pygame.draw.rect(screen, (100, 100, 130), (WIN_X, WIN_Y, WIN_W, WIN_H), 2)

    font_hdr = _font(22)
    font_lbl = _font(20)
    font_val = _font(20)

    # Civ name headers
    for civ in game.civs:
        cx = WIN_X + LABEL_W + civ.player_index * CIV_COL_W + CIV_COL_W // 2
        col = PLAYER_COLORS[civ.player_index] if not civ.is_eliminated else (90, 90, 90)
        label = civ.name if not civ.is_eliminated else f"{civ.name} (eliminated)"
        txt = font_hdr.render(label, True, col)
        screen.blit(txt, txt.get_rect(centerx=cx, y=WIN_Y + 10))

    pygame.draw.line(screen, (80, 80, 110),
                     (WIN_X + 8, WIN_Y + HDR_H),
                     (WIN_X + WIN_W - 8, WIN_Y + HDR_H), 1)

    # Compute stats for each civ
    civ_stats = []
    for civ in game.civs:
        if civ.is_eliminated:
            civ_stats.append(None)
            continue
        mil_str = sum(UNIT_DEFS[u.unit_type]["strength"] for u in civ.units if not u.is_civilian)
        territory = sum(1 for t in game.tiles.values() if t.owner == civ.player_index)
        cap_hp = civ.original_capital.hp if civ.original_capital else 0
        gpt = sum(compute_city_yields(c, game.tiles, civ)["gold"] for c in civ.cities)
        spt = sum(compute_city_yields(c, game.tiles, civ)["science"] for c in civ.cities)
        civ_stats.append({
            "mil_str":   mil_str,
            "gold":      civ.gold,
            "gpt":       gpt,
            "cities":    len(civ.cities),
            "pop":       sum(c.population for c in civ.cities),
            "sci_pt":    spt,
            "techs":     len(civ.techs_researched),
            "territory": territory,
            "score":     compute_score(civ, game),
            "cap_hp":    cap_hp,
        })

    ROWS = [
        ("Military Strength", "mil_str",   (255, 120, 120)),
        ("Gold",              "gold",      (255, 215,   0)),
        ("Gold / Turn",       "gpt",       (220, 185,   0)),
        ("Cities",            "cities",    (180, 220, 255)),
        ("Population",        "pop",       (140, 220, 140)),
        ("Science / Turn",    "sci_pt",    (120, 180, 255)),
        ("Techs Researched",  "techs",     (200, 140, 255)),
        ("Territory",         "territory", (160, 200, 160)),
        ("Score",             "score",     (255, 200,  80)),
        ("Capital HP",        "cap_hp",    (255, 100, 100)),
    ]

    for row_i, (label, key, color) in enumerate(ROWS):
        y = WIN_Y + HDR_H + 4 + row_i * ROW_H
        if row_i % 2 == 0:
            stripe = pygame.Surface((WIN_W - 4, ROW_H - 2), pygame.SRCALPHA)
            stripe.fill((255, 255, 255, 12))
            screen.blit(stripe, (WIN_X + 2, y))

        lbl = font_lbl.render(label, True, (180, 180, 180))
        screen.blit(lbl, (WIN_X + 10, y + (ROW_H - lbl.get_height()) // 2))

        # Find the leading value among active civs
        active_vals = [civ_stats[c.player_index][key] for c in game.civs if not c.is_eliminated]
        best_val = max(active_vals) if active_vals else None

        for civ in game.civs:
            cx = WIN_X + LABEL_W + civ.player_index * CIV_COL_W + CIV_COL_W // 2
            if civ.is_eliminated:
                val_str = "—"
                val_col = (80, 80, 80)
            else:
                v = civ_stats[civ.player_index][key]
                is_leader = (best_val is not None and v == best_val)

                # Gold highlight behind leading cell
                if is_leader:
                    hl = pygame.Surface((CIV_COL_W - 4, ROW_H - 4), pygame.SRCALPHA)
                    hl.fill((255, 200, 0, 40))
                    screen.blit(hl, (WIN_X + LABEL_W + civ.player_index * CIV_COL_W + 2, y + 2))

                if key == "gpt" and v > 0:
                    val_str = f"+{v}"
                    val_col = (100, 220, 100)
                elif key == "gpt" and v < 0:
                    val_str = str(v)
                    val_col = (255, 80, 80)
                else:
                    val_str = str(v)
                    val_col = (255, 230, 100) if is_leader else color

            txt = font_val.render(val_str, True, val_col)
            screen.blit(txt, txt.get_rect(centerx=cx, centery=y + ROW_H // 2))

    hint = _font(18).render("S / ESC — close", True, (100, 100, 120))
    screen.blit(hint, (WIN_X + WIN_W - hint.get_width() - 10,
                       WIN_Y + WIN_H - hint.get_height() - 6))
