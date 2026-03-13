import pygame
from civ_game.map.hex_grid import hex_to_pixel, hex_corners
from civ_game.map.terrain import TERRAIN_COLORS, RESOURCE_COLORS, RESOURCES
from civ_game.ui.hud import render_hud

SCREEN_W = 1280
SCREEN_H = 720
HUD_HEIGHT = 120

COLOR_HEX_BORDER = (0, 0, 0)
COLOR_SELECTED   = (255, 230, 50)


def _on_screen(cx, cy, hex_size):
    margin = hex_size + 4
    return (
        -margin <= cx <= SCREEN_W + margin and
        -margin <= cy <= SCREEN_H - HUD_HEIGHT + margin
    )


def render(screen, game, camera, ui_state):
    screen.fill((10, 10, 20))

    hs = camera.effective_hex_size()
    ox = camera.offset_x
    oy = camera.offset_y

    selected_qr = (ui_state.selected_tile.q, ui_state.selected_tile.r) \
        if ui_state.selected_tile else None

    # --- Layer 1: Terrain hexes ---
    for (q, r), tile in game.tiles.items():
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        color = TERRAIN_COLORS[tile.terrain]
        corners = hex_corners(cx, cy, hs)
        pygame.draw.polygon(screen, color, corners)
        pygame.draw.polygon(screen, COLOR_HEX_BORDER, corners, 1)

    # --- Layer 2: Resource dots ---
    for (q, r), tile in game.tiles.items():
        if not tile.resource:
            continue
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        if not _on_screen(cx, cy, hs):
            continue
        # For Phase 1, show all resources (no tech visibility check yet)
        dot_color = RESOURCE_COLORS[tile.resource]
        dot_r = max(3, hs // 7)
        pygame.draw.circle(screen, dot_color, (int(cx + hs * 0.28), int(cy - hs * 0.28)), dot_r)
        pygame.draw.circle(screen, (0, 0, 0), (int(cx + hs * 0.28), int(cy - hs * 0.28)), dot_r, 1)

    # --- Layer 3: Selected tile highlight ---
    if selected_qr and selected_qr in game.tiles:
        q, r = selected_qr
        cx, cy = hex_to_pixel(q, r, ox, oy, hs)
        corners = hex_corners(cx, cy, hs)
        pygame.draw.polygon(screen, COLOR_SELECTED, corners, 3)

    # --- Layer 4: HUD ---
    render_hud(screen, game, ui_state)

    pygame.display.flip()
