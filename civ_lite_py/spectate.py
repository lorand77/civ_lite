"""
spectate.py — AI spectator mode entry point.

Runs a 4-AI-player game fully zoomed out so the entire map is visible.
No terrain images; hexes are drawn with muted flat colors.
Cities = colored squares (size ∝ population).
Units  = colored circles (size ∝ strength).
         Ranged units have a white concentric ring.
         Civilians are small grey circles.

Controls:
  ESC / close window  — quit
  SPACE               — pause / unpause
  +  /  =             — increase speed
  -                   — decrease speed
"""

import math
import sys
from collections import defaultdict

import pygame

from civ_game.game import Game, PLAYER_COLORS, PLAYER_NAMES
from civ_game.map.hex_grid import hex_to_pixel, hex_corners
from civ_game.data.units import UNIT_DEFS
from civ_game.systems.ai_a import ai_take_turn as ai_a_take_turn  # AI A: players 2, 3
from civ_game.systems.ai_b import ai_take_turn as ai_b_take_turn  # AI B: players 0, 1
from civ_game.systems.score import compute_score

# ── constants ────────────────────────────────────────────────────────────────

SCREEN_W = 1850
SCREEN_H = 1000
HUD_H    = 46          # thin info bar at top
MAP_AREA_Y = HUD_H     # map starts below HUD
MAP_AREA_H = SCREEN_H - HUD_H

PADDING  = 24          # pixels of breathing room around the map

BG_COLOR      = (20, 20, 28)
GRID_COLOR    = (70, 70, 80)
HUD_BG        = (18, 18, 26)
HUD_TEXT      = (210, 210, 210)
GOLD_COLOR    = (255, 215, 0)
WHITE         = (255, 255, 255)

# Muted / desaturated terrain palette — pushed to background
TERRAIN_COLORS_MUTED = {
    "grassland": (155, 192, 145),
    "plains":    (205, 212, 178),
    "hills":     (180, 157, 122),
    "forest":    (120, 152, 112),
    "ocean":     (138, 168, 202),
}

# Speed presets: (label, max_fps)  — 0 = uncapped
SPEED_PRESETS = [("> ×1", 10), ("> ×2", 20), ("> ×4", 40), ("> ×8", 80), ("> MAX", 0)]
DEFAULT_SPEED = 2   # index into SPEED_PRESETS


# ── layout ───────────────────────────────────────────────────────────────────

def compute_layout(game):
    """
    Derive hex_size and (offset_x, offset_y) so the whole map fits in
    the area [0, SCREEN_W] × [MAP_AREA_Y, SCREEN_H] with PADDING margins.
    Returns (hex_size, offset_x, offset_y).
    """
    # Bounding box with unit hex_size so we can scale
    min_x = min_y =  math.inf
    max_x = max_y = -math.inf
    for (q, r) in game.tiles:
        px, py = hex_to_pixel(q, r, 0, 0, 1)
        if px < min_x: min_x = px
        if py < min_y: min_y = py
        if px > max_x: max_x = px
        if py > max_y: max_y = py

    # Add ~1 unit of hex radius margin on each side
    min_x -= 1.2; min_y -= 1.2
    max_x += 1.2; max_y += 1.2

    map_w_unit = max_x - min_x
    map_h_unit = max_y - min_y

    avail_w = SCREEN_W   - 2 * PADDING
    avail_h = MAP_AREA_H - 2 * PADDING

    hex_size = min(avail_w / map_w_unit, avail_h / map_h_unit)

    # Centre the map in the available area
    rendered_w = map_w_unit * hex_size
    rendered_h = map_h_unit * hex_size
    offset_x = PADDING + (avail_w - rendered_w) / 2 - min_x * hex_size
    offset_y = MAP_AREA_Y + PADDING + (avail_h - rendered_h) / 2 - min_y * hex_size

    return hex_size, offset_x, offset_y


# ── rendering helpers ─────────────────────────────────────────────────────────

def _font(size):
    return pygame.font.SysFont("Arial", size, bold=False)


def draw_terrain(surface, game, hex_size, offset_x, offset_y):
    """Draw flat-color hex polygons for all tiles."""
    for (q, r), tile in game.tiles.items():
        cx, cy = hex_to_pixel(q, r, offset_x, offset_y, hex_size)
        corners = hex_corners(cx, cy, hex_size)
        color = TERRAIN_COLORS_MUTED.get(tile.terrain, (150, 150, 150))
        pygame.draw.polygon(surface, color, corners)
        pygame.draw.polygon(surface, GRID_COLOR, corners, 1)


def draw_entities(surface, game, hex_size, offset_x, offset_y):
    """
    Draw cities (squares) and units (circles) onto a per-frame SRCALPHA
    overlay so they blend with each other when stacked.
    """
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

    # ── cities ───────────────────────────────────────────────────────────────
    for civ in game.civs:
        if civ.is_eliminated:
            continue
        r_col, g_col, b_col = PLAYER_COLORS[civ.player_index]
        dark = (max(0, r_col - 60), max(0, g_col - 60), max(0, b_col - 60))

        for city in civ.cities:
            cx, cy = hex_to_pixel(city.q, city.r, offset_x, offset_y, hex_size)
            side = int(max(12, 10 + city.population * 6))
            half = side // 2
            rect = pygame.Rect(int(cx) - half, int(cy) - half, side, side)

            pygame.draw.rect(overlay, (*PLAYER_COLORS[civ.player_index], 200), rect)
            pygame.draw.rect(overlay, (*dark, 255), rect, 1)

            # Gold dot for original capital
            if city.is_original_capital:
                pygame.draw.circle(overlay, (*GOLD_COLOR, 230),
                                   (int(cx), int(cy)), max(2, side // 5))

    # ── units ────────────────────────────────────────────────────────────────
    # Collect all city hexes so we can suppress units drawn on top of them
    city_hexes = {
        (city.q, city.r)
        for civ in game.civs
        for city in civ.cities
    }

    # Group units per hex so we can offset stacked ones
    hex_units: dict[tuple, list] = defaultdict(list)
    for civ in game.civs:
        if civ.is_eliminated:
            continue
        for unit in civ.units:
            if unit.is_civilian:
                continue
            if (unit.q, unit.r) not in city_hexes:
                hex_units[(unit.q, unit.r)].append((civ.player_index, unit))

    # Small spiral offsets for stacked units (index 0 stays centred)
    STACK_OFFSETS = [(0, 0), (8, -8), (-8, 8), (8, 8), (-8, -8), (0, -10), (0, 10)]

    for (q, r), unit_list in hex_units.items():
        cx, cy = hex_to_pixel(q, r, offset_x, offset_y, hex_size)

        for idx, (pid, unit) in enumerate(unit_list):
            udef = UNIT_DEFS.get(unit.unit_type, {})
            utype = udef.get("type", "melee")
            strength = udef.get("strength", 5)

            dx, dy = STACK_OFFSETS[idx % len(STACK_OFFSETS)]
            ux = int(cx + dx)
            uy = int(cy + dy)

            radius = max(8, int(strength * 0.9))
            col = PLAYER_COLORS[pid]

            # Fill
            pygame.draw.circle(overlay, (*col, 170), (ux, uy), radius)

            # Border
            dark = (max(0, col[0]-60), max(0, col[1]-60), max(0, col[2]-60))
            pygame.draw.circle(overlay, (*dark, 220), (ux, uy), radius, 1)

            # Ranged marker: white outer ring
            if utype == "ranged":
                pygame.draw.circle(overlay, (255, 255, 255, 200),
                                   (ux, uy), radius + 2, 1)

    surface.blit(overlay, (0, 0))


def draw_hud(surface, game, speed_idx, paused, font_sm, font_md):
    """Thin top bar: turn | civ summaries | speed | controls."""
    pygame.draw.rect(surface, HUD_BG, (0, 0, SCREEN_W, HUD_H))

    # Turn
    turn_txt = font_md.render(f"Turn {game.turn}", True, HUD_TEXT)
    surface.blit(turn_txt, (10, (HUD_H - turn_txt.get_height()) // 2))

    # Civ summary blocks
    block_w = 250
    start_x = 120
    for civ in game.civs:
        col = PLAYER_COLORS[civ.player_index]
        x = start_x + civ.player_index * block_w
        city_count = len(civ.cities)
        unit_count = sum(1 for u in civ.units if not u.is_civilian)
        if civ.is_eliminated:
            label = f"{PLAYER_NAMES[civ.player_index]}: eliminated"
            txt = font_sm.render(label, True, (120, 120, 120))
        else:
            score = compute_score(civ, game)
            label = f"{PLAYER_NAMES[civ.player_index]}  C:{city_count}  U:{unit_count}  {score}pt"
            txt = font_sm.render(label, True, col)
        surface.blit(txt, (x, (HUD_H - txt.get_height()) // 2))

    # Speed / pause indicator (right side)
    speed_label = SPEED_PRESETS[speed_idx][0]
    status = "PAUSED" if paused else speed_label
    status_col = (255, 200, 50) if paused else (160, 220, 160)
    st = font_md.render(status, True, status_col)
    st_x = SCREEN_W - st.get_width() - 10
    surface.blit(st, (st_x, (HUD_H - st.get_height()) // 2))

    hint = font_sm.render("SPC=pause  +/-=speed  ESC=quit", True, (100, 100, 110))
    surface.blit(hint, (st_x - hint.get_width() - 16, (HUD_H - hint.get_height()) // 2))


def draw_score_bars(surface, game):
    """Small horizontal bar chart in the bottom-right corner, no text."""
    BAR_H     = 14
    BAR_GAP   = 3
    MAX_W     = 220
    PAD       = 12

    scores = [compute_score(civ, game) for civ in game.civs]
    max_score = max(scores) if any(scores) else 1

    total_h = len(game.civs) * BAR_H + (len(game.civs) - 1) * BAR_GAP
    x0 = SCREEN_W - MAX_W - PAD
    y0 = SCREEN_H - total_h - PAD

    for i, civ in enumerate(game.civs):
        bar_w = int(MAX_W * scores[i] / max_score)
        y = y0 + i * (BAR_H + BAR_GAP)
        col = PLAYER_COLORS[civ.player_index]
        pygame.draw.rect(surface, col, (x0, y, bar_w, BAR_H))


def draw_win_screen(surface, winner_id, turn, font_lg, font_md):
    """Simple win overlay."""
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surface.blit(overlay, (0, 0))

    col = PLAYER_COLORS[winner_id]
    msg1 = font_lg.render("VICTORY!", True, GOLD_COLOR)
    msg2 = font_md.render(f"{PLAYER_NAMES[winner_id]} achieves Domination on turn {turn}!", True, col)
    msg3 = font_md.render("Press ESC or close window to exit.", True, HUD_TEXT)

    cy = SCREEN_H // 2
    surface.blit(msg1, (SCREEN_W // 2 - msg1.get_width() // 2, cy - 80))
    surface.blit(msg2, (SCREEN_W // 2 - msg2.get_width() // 2, cy))
    surface.blit(msg3, (SCREEN_W // 2 - msg3.get_width() // 2, cy + 60))


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("CivPy — Spectator")
    clock = pygame.time.Clock()

    font_sm = _font(23)
    font_md = _font(30)
    font_lg = _font(108)

    # All 4 players are CPU
    game = Game(
        num_players=4,
        map_cols=32,
        map_rows=20,
        seed=None,
        cpu_flags=[True, True, True, True],
    )

    hex_size, offset_x, offset_y = compute_layout(game)

    paused     = False
    speed_idx  = DEFAULT_SPEED
    game_over  = False

    while True:
        # ── events ────────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    speed_idx = min(speed_idx + 1, len(SPEED_PRESETS) - 1)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed_idx = max(speed_idx - 1, 0)

        # ── advance game ──────────────────────────────────────────────────────
        if not paused and not game_over:
            civ = game.civs[game.current_player]
            if not civ.is_eliminated:
                (ai_a_take_turn if civ.player_index >= 2 else ai_b_take_turn)(game, civ)
            game.end_turn()
            if game.winner is not None:
                game_over = True

        # ── render ────────────────────────────────────────────────────────────
        screen.fill(BG_COLOR)
        draw_terrain(screen, game, hex_size, offset_x, offset_y)
        draw_entities(screen, game, hex_size, offset_x, offset_y)
        draw_hud(screen, game, speed_idx, paused, font_sm, font_md)
        draw_score_bars(screen, game)

        if game_over:
            draw_win_screen(screen, game.winner, game.turn, font_lg, font_md)

        pygame.display.flip()

        fps_cap = SPEED_PRESETS[speed_idx][1]
        clock.tick(fps_cap if fps_cap > 0 else 0)


if __name__ == "__main__":
    main()
