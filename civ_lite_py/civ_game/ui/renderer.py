import pygame
from civ_game.map.hex_grid import hex_to_pixel, hex_corners, HEX_DIRECTIONS
from civ_game.map.terrain import TERRAIN_COLORS, RESOURCE_COLORS
from civ_game.data.units import UNIT_DEFS
from civ_game.entities.improvement import IMPROVEMENT_DEFS
from civ_game.map.terrain import RESOURCES
from civ_game.ui.hud import render_hud
from civ_game.ui.city_screen import render_city_screen, set_tiles
from civ_game.ui.tech_screen import render_tech_screen

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
        dot_color = RESOURCE_COLORS[tile.resource]
        dr = max(3, hs // 7)
        dx, dy = int(cx + hs * 0.28), int(cy - hs * 0.28)
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

    # --- Layer 12: Combat message ---
    if ui_state.message_timer > 0:
        ui_state.message_timer -= 1
        msg_surf = _font(28).render(ui_state.message, True, (255, 230, 100))
        mx = SCREEN_W // 2 - msg_surf.get_width() // 2
        my = (SCREEN_H - HUD_HEIGHT) // 2 - 20
        bg = pygame.Surface((msg_surf.get_width() + 20, msg_surf.get_height() + 10),
                             pygame.SRCALPHA)
        bg.fill((0, 0, 0, 160))
        screen.blit(bg, (mx - 10, my - 5))
        screen.blit(msg_surf, (mx, my))

    # --- Layer 13: Win screen ---
    if game.winner is not None:
        _render_win_screen(screen, game.winner)

    pygame.display.flip()


def _draw_hp_bar_inline(screen, x, y, hp, max_hp, width=40):
    filled = max(0, int(width * hp / max_hp))
    pygame.draw.rect(screen, (80, 20, 20), (x, y, width, 5))
    pygame.draw.rect(screen, (220, 60, 60), (x, y, filled, 5))
    pygame.draw.rect(screen, (140, 140, 140), (x, y, width, 5), 1)


def _render_win_screen(screen, winner):
    from civ_game.game import PLAYER_NAMES, PLAYER_COLORS

    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 190))
    screen.blit(overlay, (0, 0))

    cname = PLAYER_NAMES[winner]
    color = PLAYER_COLORS[winner]

    title = _font(90).render("VICTORY!", True, (255, 215, 0))
    sub   = _font(44).render(f"{cname} achieves Domination!", True, color)
    hint  = _font(30).render("Close the window to exit.", True, (180, 180, 180))

    cx = SCREEN_W // 2
    cy = SCREEN_H // 2
    screen.blit(title, title.get_rect(center=(cx, cy - 70)))
    screen.blit(sub,   sub.get_rect(center=(cx, cy + 20)))
    screen.blit(hint,  hint.get_rect(center=(cx, cy + 80)))
