import math
import os
import pygame
from civ_game.map.hex_grid import hex_to_pixel, hex_corners, HEX_DIRECTIONS
from civ_game.map.terrain import TERRAIN_COLORS, RESOURCE_COLORS
from civ_game.data.units import UNIT_DEFS
from civ_game.entities.improvement import IMPROVEMENT_DEFS
from civ_game.map.terrain import RESOURCES
from civ_game.ui.hud import render_hud
from civ_game.ui.city_screen import render_city_screen, set_tiles
from civ_game.ui.tech_screen import render_tech_screen

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")

_TERRAIN_IMAGE_FILES = {
    "grassland": "terrain-grassland.png",
    "plains":    "terrain-plains.png",
    "forest":    "terrain-forest.png",
    "hills":     "terrain-hills.png",
    "ocean":     "terrain-ocean.png",
}

_raw_images: dict = {}          # terrain -> raw Surface
_hex_surface_cache: dict = {}   # (terrain, hs) -> masked SRCALPHA Surface

_RESOURCE_IMAGE_FILES = {
    "gold":     "resource-Gold.png",
    "silver":   "resource-Silver.png",
    "iron":     "resource-Iron.png",
    "horses":   "resource-Horses.png",
    "diamonds": "resource-Diamonds.png",
}

_resource_raw: dict = {}    # resource -> raw Surface (loaded once)
_resource_icons: dict = {}  # (resource, size) -> scaled Surface


def _get_resource_icon(resource: str, hs: int):
    """Return a resource icon scaled proportionally to hs (20px at hs=43)."""
    size = max(20, round(20 * hs / 43))
    key = (resource, size)
    if key in _resource_icons:
        return _resource_icons[key]

    if resource not in _resource_raw:
        fname = _RESOURCE_IMAGE_FILES.get(resource)
        if not fname:
            _resource_raw[resource] = None
        else:
            path = os.path.join(_ASSETS_DIR, fname)
            try:
                _resource_raw[resource] = pygame.image.load(path).convert_alpha()
            except Exception:
                _resource_raw[resource] = None

    raw = _resource_raw.get(resource)
    if raw is None:
        _resource_icons[key] = None
        return None

    _resource_icons[key] = pygame.transform.scale(raw, (size, size))
    return _resource_icons[key]


def _get_terrain_surface(terrain: str, hs: int):
    """Return a hex-masked terrain image surface, or None if no image exists."""
    key = (terrain, hs)
    if key in _hex_surface_cache:
        return _hex_surface_cache[key]

    fname = _TERRAIN_IMAGE_FILES.get(terrain)
    if not fname:
        _hex_surface_cache[key] = None
        return None

    if terrain not in _raw_images:
        path = os.path.join(_ASSETS_DIR, fname)
        try:
            _raw_images[terrain] = pygame.image.load(path).convert_alpha()
        except Exception:
            _raw_images[terrain] = None

    raw = _raw_images.get(terrain)
    if raw is None:
        _hex_surface_cache[key] = None
        return None

    # Bounding box for this hex size
    bw = math.ceil(math.sqrt(3) * hs)
    bh = 2 * hs

    scaled = pygame.transform.scale(raw, (bw, bh))

    # Hex corners relative to bounding box center
    cx_local = bw / 2
    cy_local = bh / 2
    local_corners = [
        (cx_local + hs * math.cos(math.radians(60 * i - 30)),
         cy_local + hs * math.sin(math.radians(60 * i - 30)))
        for i in range(6)
    ]

    # Draw image, then punch out a hex-shaped alpha mask
    surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
    surf.blit(scaled, (0, 0))

    mask = pygame.Surface((bw, bh), pygame.SRCALPHA)
    mask.fill((0, 0, 0, 0))
    pygame.draw.polygon(mask, (255, 255, 255, 255), local_corners)

    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    _hex_surface_cache[key] = surf
    return surf

SCREEN_W = 1850
SCREEN_H = 1000
HUD_HEIGHT = 180

# For pointy-top hex: edge i (shared with HEX_DIRECTIONS[i]) connects these corner indices
_EDGE_CORNERS = [(0, 1), (5, 0), (4, 5), (3, 4), (2, 3), (1, 2)]

COLOR_HEX_BORDER    = (0, 0, 0)
COLOR_SELECTED      = (255, 230, 50)
COLOR_MOVE_FILL     = (255, 255, 100, 55)
COLOR_MOVE_BORDER   = (255, 255, 100)
COLOR_ATTACK_FILL   = (255, 80, 80, 55)
COLOR_ATTACK_BORDER = (255, 80, 80)

PLAYER_COLORS = [
    (220, 50,  50),
    (50,  100, 220),
    (50,  180, 50),
    (220, 180, 50),
]

_font_cache: dict = {}

def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def _on_screen(cx, cy, hs):
    m = hs + 4
    return -m <= cx <= SCREEN_W + m and -m <= cy <= SCREEN_H - HUD_HEIGHT + m


def render(screen, game, camera, ui_state):
    screen.fill((10, 10, 20))

    hs = camera.effective_hex_size()
    ox, oy = camera.offset_x, camera.offset_y

    selected_qr = None
    if ui_state.selected_unit:
        u = ui_state.selected_unit
        selected_qr = (u.q, u.r)
    elif ui_state.selected_tile:
        selected_qr = (ui_state.selected_tile.q, ui_state.selected_tile.r)

    # --- Layer 1: Terrain ---
    for (q, r), tile in game.tiles.items():
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        terrain_surf = _get_terrain_surface(tile.terrain, hs)
        if terrain_surf:
            bw, bh = terrain_surf.get_size()
            screen.blit(terrain_surf, (cx - bw // 2, cy - bh // 2))
        else:
            pygame.draw.polygon(screen, TERRAIN_COLORS[tile.terrain], hex_corners(cx, cy, hs))
        pygame.draw.polygon(screen, COLOR_HEX_BORDER, hex_corners(cx, cy, hs), 1)

    # --- Layer 2b: Territory border lines ---
    for (q, r), tile in game.tiles.items():
        if tile.owner is None:
            continue
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        corners = hex_corners(cx, cy, hs)
        border_color = PLAYER_COLORS[tile.owner]
        border_w = max(2, hs // 18)
        for i, (dq, dr) in enumerate(HEX_DIRECTIONS):
            nb = game.tiles.get((q + dq, r + dr))
            nb_owner = nb.owner if nb else None
            if nb_owner != tile.owner:
                c0, c1 = _EDGE_CORNERS[i]
                pygame.draw.line(screen, border_color,
                                 (int(corners[c0][0]), int(corners[c0][1])),
                                 (int(corners[c1][0]), int(corners[c1][1])),
                                 border_w)

    # --- Layer 3: Resources (only if revealed to current player) ---
    current_techs = game.current_civ().techs_researched
    for (q, r), tile in game.tiles.items():
        if not tile.resource:
            continue
        res_def = RESOURCES.get(tile.resource, {})
        req_tech = res_def.get("requires_tech")
        if req_tech and req_tech not in current_techs:
            continue  # not yet revealed to this player
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        dx, dy = int(cx + hs * 0.28), int(cy - hs * 0.28)
        icon = _get_resource_icon(tile.resource, hs)
        if icon:
            half = icon.get_width() // 2
            screen.blit(icon, (dx - half, dy - half))
        else:
            dot_color = RESOURCE_COLORS[tile.resource]
            dr = max(3, hs // 7)
            pygame.draw.circle(screen, dot_color, (dx, dy), dr)
            pygame.draw.circle(screen, (0, 0, 0), (dx, dy), dr, 1)

    # --- Layer 4: Improvement labels ---
    for (q, r), tile in game.tiles.items():
        if not tile.improvement:
            continue
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        label = IMPROVEMENT_DEFS[tile.improvement]["label"]
        surf = _font(24).render(label, True, (220, 220, 100))
        screen.blit(surf, (int(cx) - surf.get_width() // 2 - int(hs * 0.3),
                           int(cy) + int(hs * 0.3)))

    # --- Layer 5: Movement + attack range highlights ---
    if ui_state.reachable_tiles or ui_state.attackable_tiles:
        overlay_surf = pygame.Surface((SCREEN_W, SCREEN_H - HUD_HEIGHT), pygame.SRCALPHA)
        for (q, r) in ui_state.reachable_tiles:
            cx, cy = hex_to_pixel(q, r, ox, oy, hs)
            if not _on_screen(cx, cy, hs):
                continue
            pygame.draw.polygon(overlay_surf, COLOR_MOVE_FILL, hex_corners(cx, cy, hs))
            pygame.draw.polygon(overlay_surf, (*COLOR_MOVE_BORDER, 200), hex_corners(cx, cy, hs), 2)
        for (q, r) in ui_state.attackable_tiles:
            cx, cy = hex_to_pixel(q, r, ox, oy, hs)
            if not _on_screen(cx, cy, hs):
                continue
            pygame.draw.polygon(overlay_surf, COLOR_ATTACK_FILL, hex_corners(cx, cy, hs))
            pygame.draw.polygon(overlay_surf, (*COLOR_ATTACK_BORDER, 220), hex_corners(cx, cy, hs), 3)
        screen.blit(overlay_surf, (0, 0))

    # --- Layer 6: Cities ---
    for civ in game.civs:
        for city in civ.cities:
            cx, cy = hex_to_pixel(city.q, city.r, ox, oy, hs)
            if not _on_screen(cx, cy, hs):
                continue
            r_city = max(8, hs // 3)
            pygame.draw.circle(screen, civ.color, (int(cx), int(cy)), r_city)
            pygame.draw.circle(screen, (0, 0, 0), (int(cx), int(cy)), r_city, 2)
            # Original capital marker: gold ring
            if city.is_original_capital:
                pygame.draw.circle(screen, (255, 215, 0), (int(cx), int(cy)), r_city + 3, 2)
            # Name above
            name_surf = _font(24).render(city.name, True, (255, 255, 255))
            screen.blit(name_surf, (int(cx) - name_surf.get_width() // 2,
                                    int(cy) - r_city - 22))
            # Population inside
            pop_surf = _font(24).render(str(city.population), True, (255, 255, 255))
            screen.blit(pop_surf, (int(cx) - pop_surf.get_width() // 2,
                                   int(cy) - pop_surf.get_height() // 2))
            # HP bar (only when damaged)
            if city.hp < 50:
                bar_w = r_city * 2 + 4
                bx = int(cx) - r_city - 2
                by = int(cy) + r_city + 3
                _draw_hp_bar_inline(screen, bx, by, city.hp, 50, bar_w)

    # --- Layer 7: Units ---
    for civ in game.civs:
        for unit in civ.units:
            cx, cy = hex_to_pixel(unit.q, unit.r, ox, oy, hs)
            if not _on_screen(cx, cy, hs):
                continue
            offset = (int(hs * 0.22), int(hs * 0.22)) if unit.is_civilian else (0, 0)
            ux, uy = int(cx) + offset[0], int(cy) + offset[1]
            r_unit = max(7, hs // 4)
            pygame.draw.circle(screen, civ.color, (ux, uy), r_unit)
            pygame.draw.circle(screen, (0, 0, 0), (ux, uy), r_unit, 2)
            # Fortified ring (blue) / healing ring (green)
            if unit.fortified:
                pygame.draw.circle(screen, (200, 200, 255), (ux, uy), r_unit + 2, 2)
            elif unit.healing:
                pygame.draw.circle(screen, (80, 220, 80), (ux, uy), r_unit + 2, 2)
            lbl = _font(22).render(unit.label, True, (255, 255, 255))
            screen.blit(lbl, (ux - lbl.get_width() // 2, uy - lbl.get_height() // 2))
            # Grey out if no moves left (current player only)
            if unit.moves_left == 0 and unit.owner == game.current_player:
                dim = pygame.Surface((r_unit * 2, r_unit * 2), pygame.SRCALPHA)
                pygame.draw.circle(dim, (0, 0, 0, 100), (r_unit, r_unit), r_unit)
                screen.blit(dim, (ux - r_unit, uy - r_unit))
            # Building indicator
            if unit.building_improvement:
                ind = _font(20).render(f"[{unit.build_turns_left}]", True, (255, 220, 80))
                screen.blit(ind, (ux + r_unit, uy - r_unit))
            # HP bar (only when damaged)
            from civ_game.data.units import UNIT_DEFS as _UD
            hp_max = _UD[unit.unit_type]["hp_max"]
            if unit.hp < hp_max:
                bar_w = r_unit * 2 + 4
                bx = ux - r_unit - 2
                by = uy + r_unit + 3
                _draw_hp_bar_inline(screen, bx, by, unit.hp, hp_max, bar_w)

    # --- Layer 8: Selection ring ---
    if selected_qr and selected_qr in game.tiles:
        q, r = selected_qr
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        pygame.draw.polygon(screen, COLOR_SELECTED, hex_corners(cx, cy, hs), 3)

    # --- Layer 9: HUD ---
    render_hud(screen, game, ui_state)

    # --- Layer 10: Tech screen ---
    if ui_state.tech_screen_open:
        render_tech_screen(screen, game.current_civ(), ui_state)

    # --- Layer 11: City screen ---
    if ui_state.city_screen_open and ui_state.selected_city:
        set_tiles(game.tiles)
        render_city_screen(screen, ui_state.selected_city,
                           game.civs[ui_state.selected_city.owner], ui_state)

    # --- Layer 12: Notification popup (supports multi-line) ---
    if ui_state.message_timer > 0:
        ui_state.message_timer -= 1
        lines = ui_state.message.split("\n")
        line_surfs = [_font(28).render(ln, True, (255, 230, 100)) for ln in lines]
        pad = 14
        line_h = line_surfs[0].get_height() + 4
        total_h = line_h * len(line_surfs) + pad
        total_w = max(s.get_width() for s in line_surfs) + pad * 2
        bx = SCREEN_W // 2 - total_w // 2
        by = (SCREEN_H - HUD_HEIGHT) // 3
        bg = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 180))
        screen.blit(bg, (bx, by))
        pygame.draw.rect(screen, (200, 180, 80), (bx, by, total_w, total_h), 1)
        for i, surf in enumerate(line_surfs):
            screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2,
                               by + pad // 2 + i * line_h))

    # --- Layer 13: Turn banner (hotseat handoff) ---
    if ui_state.turn_banner_timer > 0:
        _render_turn_banner(screen, game)
        ui_state.turn_banner_timer -= 1
        if ui_state.turn_banner_timer == 0:
            # Banner just expired naturally — promote any queued message
            if ui_state.queued_message:
                ui_state.set_message(ui_state.queued_message)
                ui_state.queued_message = ""
            if ui_state.auto_open_tech:
                ui_state.tech_screen_open = True
                ui_state.auto_open_tech = False

    # --- Layer 14: Scoreboard ---
    _render_scoreboard(screen, game)

    # --- Layer 15: Win screen ---
    if game.winner is not None:
        _render_win_screen(screen, game.winner)

    pygame.display.flip()


def _draw_hp_bar_inline(screen, x, y, hp, max_hp, width=40):
    filled = max(0, int(width * hp / max_hp))
    pygame.draw.rect(screen, (80, 20, 20), (x, y, width, 5))
    pygame.draw.rect(screen, (220, 60, 60), (x, y, filled, 5))
    pygame.draw.rect(screen, (140, 140, 140), (x, y, width, 5), 1)


def _render_turn_banner(screen, game):
    from civ_game.game import PLAYER_NAMES, PLAYER_COLORS as _PC

    player = game.current_player
    color  = _PC[player]
    name   = PLAYER_NAMES[player]

    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    cx = SCREEN_W // 2
    cy = SCREEN_H // 2

    title = _font(80).render(f"{name}'s Turn", True, color)
    sub   = _font(30).render(f"Turn {game.turn}  —  click or press any key to continue",
                             True, (200, 200, 200))

    pygame.draw.rect(screen, (20, 20, 30),
                     (cx - title.get_width() // 2 - 30, cy - 70,
                      title.get_width() + 60, title.get_height() + sub.get_height() + 30),
                     border_radius=10)
    pygame.draw.rect(screen, color,
                     (cx - title.get_width() // 2 - 30, cy - 70,
                      title.get_width() + 60, title.get_height() + sub.get_height() + 30),
                     3, border_radius=10)

    screen.blit(title, title.get_rect(center=(cx, cy - 20)))
    screen.blit(sub,   sub.get_rect(center=(cx, cy + title.get_height() // 2 + 10)))


def _compute_score(civ, game) -> int:
    from civ_game.data.buildings import BUILDING_DEFS
    from civ_game.data.units import UNIT_DEFS as _UD

    score = 0
    score += len(civ.cities) * 50
    score += sum(c.population for c in civ.cities) * 20
    score += sum(_UD[u.unit_type]["strength"] for u in civ.units if not u.is_civilian) * 3
    score += len(civ.techs_researched) * 20
    score += sum(1 for t in game.tiles.values() if t.owner == civ.player_index)
    score += civ.gold // 10

    for city in civ.cities:
        for b_key in city.buildings:
            defn = BUILDING_DEFS[b_key]
            effects = defn.get("effects", {})
            score += effects.get("food_per_turn",    0) * 4
            score += effects.get("prod_per_turn",    0) * 5
            score += effects.get("gold_per_turn",    0) * 3
            score += effects.get("science_per_turn", 0) * 6
            score += effects.get("culture_per_turn", 0) * 2
            score += defn.get("defense", 0) * 8

    return score


def _render_scoreboard(screen, game):
    panel_w = 280
    row_h   = 36
    pad     = 10
    panel_h = pad + 30 + pad + row_h * len(game.civs) + pad
    panel_x = SCREEN_W - panel_w - 10
    panel_y = 10

    # Background
    bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    bg.fill((15, 15, 25, 210))
    screen.blit(bg, (panel_x, panel_y))
    pygame.draw.rect(screen, (80, 80, 110), (panel_x, panel_y, panel_w, panel_h), 1)

    # Title
    title = _font(22).render("SCORES", True, (200, 200, 220))
    screen.blit(title, title.get_rect(
        centerx=panel_x + panel_w // 2, top=panel_y + pad))

    # Divider
    dy = panel_y + pad + 26
    pygame.draw.line(screen, (70, 70, 100),
                     (panel_x + 8, dy), (panel_x + panel_w - 8, dy), 1)

    # Compute and sort
    entries = sorted(
        [(civ, _compute_score(civ, game)) for civ in game.civs],
        key=lambda x: x[1], reverse=True
    )

    for rank, (civ, score) in enumerate(entries):
        ry = dy + pad + rank * row_h
        color = civ.color if not civ.is_eliminated else (80, 80, 80)

        # Color swatch
        pygame.draw.rect(screen, color, (panel_x + 10, ry + 8, 16, 16))

        # Name
        name_surf = _font(20).render(civ.name, True, color)
        screen.blit(name_surf, (panel_x + 34, ry + 8))

        # Score (right-aligned)
        label = "eliminated" if civ.is_eliminated else str(score)
        score_surf = _font(20).render(label, True, color)
        screen.blit(score_surf, (panel_x + panel_w - score_surf.get_width() - 10, ry + 8))


WIN_EXIT_RECT = pygame.Rect(SCREEN_W // 2 - 100, SCREEN_H // 2 + 110, 200, 48)


def _render_win_screen(screen, winner):
    from civ_game.game import PLAYER_NAMES, PLAYER_COLORS

    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    screen.blit(overlay, (0, 0))

    cname = PLAYER_NAMES[winner]
    color = PLAYER_COLORS[winner]

    title = _font(90).render("VICTORY!", True, (255, 215, 0))
    sub   = _font(44).render(f"{cname} achieves Domination!", True, color)

    cx = SCREEN_W // 2
    cy = SCREEN_H // 2
    screen.blit(title, title.get_rect(center=(cx, cy - 70)))
    screen.blit(sub,   sub.get_rect(center=(cx, cy + 20)))

    # Exit button
    mp = pygame.mouse.get_pos()
    btn_color = (160, 50, 50) if WIN_EXIT_RECT.collidepoint(mp) else (110, 30, 30)
    pygame.draw.rect(screen, btn_color, WIN_EXIT_RECT, border_radius=6)
    pygame.draw.rect(screen, (200, 80, 80), WIN_EXIT_RECT, 2, border_radius=6)
    lbl = _font(28).render("Exit Game", True, (255, 255, 255))
    screen.blit(lbl, lbl.get_rect(center=WIN_EXIT_RECT.center))
