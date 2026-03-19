import pygame
import sys

SCREEN_W = 1850
SCREEN_H = 1000

PANEL_W  = 500
PANEL_H  = 380
PANEL_X  = (SCREEN_W - PANEL_W) // 2
PANEL_Y  = (SCREEN_H - PANEL_H) // 2

# Matches game.py constants
PLAYER_NAMES  = ["Rome", "Greece", "The Huns", "Babylon"]
PLAYER_COLORS = [(220, 50, 50), (50, 100, 220), (50, 180, 50), (220, 180, 50)]

COLOR_BG      = (20, 20, 30)
COLOR_PANEL   = (30, 30, 45)
COLOR_BORDER  = (100, 100, 140)
COLOR_TEXT    = (230, 230, 230)
COLOR_HUMAN   = (40,  80, 140)
COLOR_HUMAN_H = (60, 110, 190)
COLOR_CPU     = (70,  70,  90)
COLOR_CPU_H   = (100, 100, 120)
COLOR_START   = (50, 110, 50)
COLOR_START_H = (70, 150, 70)

_font_cache = {}


def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def run_setup_screen(screen) -> list:
    """
    Blocking loop — renders the player setup screen and returns a list of
    4 bools: cpu_flags[i] = True means player i is CPU-controlled.
    Default: player 0 Human, players 1-3 CPU.
    """
    is_cpu = [False, True, True, True]
    clock  = pygame.time.Clock()

    while True:
        mouse = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check toggle buttons
                for i in range(4):
                    btn_rect = _toggle_rect(i)
                    if btn_rect.collidepoint(event.pos):
                        is_cpu[i] = not is_cpu[i]
                # Check Start button
                if _start_rect().collidepoint(event.pos):
                    return is_cpu

        _render(screen, is_cpu, mouse)
        pygame.display.flip()
        clock.tick(60)


def _row_y(player_index) -> int:
    """Top y of a player row inside the panel."""
    return PANEL_Y + 80 + player_index * 64


def _toggle_rect(player_index) -> pygame.Rect:
    return pygame.Rect(PANEL_X + PANEL_W - 140, _row_y(player_index) + 4, 120, 36)


def _start_rect() -> pygame.Rect:
    return pygame.Rect(PANEL_X + PANEL_W // 2 - 100, PANEL_Y + PANEL_H - 66, 200, 44)


def _render(screen, is_cpu, mouse):
    screen.fill(COLOR_BG)

    # Panel
    pygame.draw.rect(screen, COLOR_PANEL, (PANEL_X, PANEL_Y, PANEL_W, PANEL_H))
    pygame.draw.rect(screen, COLOR_BORDER, (PANEL_X, PANEL_Y, PANEL_W, PANEL_H), 2)

    # Title
    title = _font(34).render("CivPy  —  Player Setup", True, COLOR_TEXT)
    screen.blit(title, title.get_rect(centerx=PANEL_X + PANEL_W // 2, top=PANEL_Y + 18))

    # Divider
    pygame.draw.line(screen, COLOR_BORDER,
                     (PANEL_X + 16, PANEL_Y + 60), (PANEL_X + PANEL_W - 16, PANEL_Y + 60), 1)

    # Player rows
    for i in range(4):
        row_y = _row_y(i)

        # Color swatch
        pygame.draw.rect(screen, PLAYER_COLORS[i], (PANEL_X + 24, row_y + 8, 22, 22))

        # Name
        name_surf = _font(26).render(PLAYER_NAMES[i], True, PLAYER_COLORS[i])
        screen.blit(name_surf, (PANEL_X + 60, row_y + 10))

        # Toggle button
        btn_rect = _toggle_rect(i)
        if is_cpu[i]:
            btn_color = COLOR_CPU_H if btn_rect.collidepoint(mouse) else COLOR_CPU
            label = "CPU"
        else:
            btn_color = COLOR_HUMAN_H if btn_rect.collidepoint(mouse) else COLOR_HUMAN
            label = "Human"
        pygame.draw.rect(screen, btn_color, btn_rect, border_radius=4)
        pygame.draw.rect(screen, COLOR_BORDER, btn_rect, 1, border_radius=4)
        lbl = _font(22).render(label, True, COLOR_TEXT)
        screen.blit(lbl, lbl.get_rect(center=btn_rect.center))

    # Start button
    sr = _start_rect()
    sc = COLOR_START_H if sr.collidepoint(mouse) else COLOR_START
    pygame.draw.rect(screen, sc, sr, border_radius=5)
    pygame.draw.rect(screen, COLOR_BORDER, sr, 1, border_radius=5)
    start_lbl = _font(26).render("Start Game", True, COLOR_TEXT)
    screen.blit(start_lbl, start_lbl.get_rect(center=sr.center))
