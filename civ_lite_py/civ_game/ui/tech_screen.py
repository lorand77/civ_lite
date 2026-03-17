import math
import pygame
from civ_game.data.techs import TECH_DEFS

PANEL_X, PANEL_Y = 125, 40
PANEL_W, PANEL_H = 1600, 720
NODE_W, NODE_H = 200, 54

# (x, y) relative to PANEL_X/PANEL_Y — top-left corner of each node rect
NODE_POSITIONS = {
    "mining":            (80,  120),
    "animal_husbandry":  (80,  250),
    "archery":           (80,  380),
    "pottery":           (80,  505),
    "bronze_working":    (360, 183),
    "iron_working":      (640, 120),
    "horseback_riding":  (640, 250),
    "writing":           (640, 460),
    "mathematics":       (920, 393),
    "currency":          (920, 520),
    # Medieval Era
    "feudalism":         (1140, 90),
    "steel":             (1140, 200),
    "machinery":         (1140, 330),
    "theology":          (1140, 440),
    "civil_service":     (1140, 570),
    "education":         (1360, 440),
}

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


def _node_rect(tech_key):
    nx, ny = NODE_POSITIONS[tech_key]
    return pygame.Rect(PANEL_X + nx, PANEL_Y + ny, NODE_W, NODE_H)


def _draw_arrowhead(screen, p1, p2, color, size=7):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = p2
    b1 = (tip[0] - ux * size + px * size * 0.45,
          tip[1] - uy * size + py * size * 0.45)
    b2 = (tip[0] - ux * size - px * size * 0.45,
          tip[1] - uy * size - py * size * 0.45)
    pygame.draw.polygon(screen, color, [tip, b1, b2])


def render_tech_screen(screen, civ, ui_state):
    researched = civ.techs_researched
    current = civ.current_research

    # Dark overlay over game area
    overlay = pygame.Surface((1850, 820), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 210))
    screen.blit(overlay, (0, 0))

    # Panel background
    pygame.draw.rect(screen, (18, 18, 32), (PANEL_X, PANEL_Y, PANEL_W, PANEL_H))
    pygame.draw.rect(screen, (90, 90, 140), (PANEL_X, PANEL_Y, PANEL_W, PANEL_H), 2)

    # Title
    title = _font(36).render("TECHNOLOGY TREE", True, (200, 200, 255))
    screen.blit(title, (PANEL_X + PANEL_W // 2 - title.get_width() // 2, PANEL_Y + 10))

    # Era labels
    screen.blit(_font(22).render("-- ANCIENT ERA --", True, (130, 130, 180)),
                (PANEL_X + 80, PANEL_Y + 80))
    screen.blit(_font(22).render("-- CLASSICAL ERA --", True, (130, 130, 180)),
                (PANEL_X + 590, PANEL_Y + 80))
    screen.blit(_font(22).render("-- MEDIEVAL ERA --", True, (130, 130, 180)),
                (PANEL_X + 1100, PANEL_Y + 50))

    # Draw prerequisite connection lines
    for tech_key, defn in TECH_DEFS.items():
        for prereq in defn["prerequisites"]:
            fr = _node_rect(prereq)
            tr = _node_rect(tech_key)
            p1 = (fr.right, fr.centery)
            p2 = (tr.left, tr.centery)
            if prereq in researched and tech_key in researched:
                line_color = (80, 180, 80)
            elif prereq in researched:
                line_color = (120, 120, 200)
            else:
                line_color = (60, 60, 60)
            pygame.draw.line(screen, line_color, p1, p2, 2)
            _draw_arrowhead(screen, p1, p2, line_color)

    # Draw tech nodes
    for tech_key in NODE_POSITIONS:
        rect = _node_rect(tech_key)
        defn = TECH_DEFS[tech_key]
        prereqs_met = all(p in researched for p in defn["prerequisites"])

        if tech_key in researched:
            bg      = (30, 70, 30)
            border  = (80, 190, 80)
            tcol    = (160, 255, 160)
            ccol    = (80, 190, 80)
        elif tech_key == current:
            t = pygame.time.get_ticks()
            pulse = abs(math.sin(t / 400.0))
            bv = int(140 + 115 * pulse)
            bg      = (25, 45, 75)
            border  = (80, bv, 255)
            tcol    = (200, 220, 255)
            ccol    = (120, 180, 255)
        elif prereqs_met:
            bg      = (35, 35, 55)
            border  = (140, 140, 210)
            tcol    = (210, 210, 255)
            ccol    = (130, 130, 170)
        else:
            bg      = (22, 22, 28)
            border  = (55, 55, 55)
            tcol    = (90, 90, 90)
            ccol    = (60, 60, 60)

        pygame.draw.rect(screen, bg, rect, border_radius=5)
        pygame.draw.rect(screen, border, rect, 2, border_radius=5)

        name_surf = _font(20).render(defn["name"], True, tcol)
        screen.blit(name_surf, (rect.x + 6, rect.y + 6))

        if tech_key in researched:
            cost_text = "Done"
        elif tech_key == current:
            cost_text = f"{civ.science}/{defn['science_cost']} sci"
        else:
            cost_text = f"{defn['science_cost']} science"
        cost_surf = _font(18).render(cost_text, True, ccol)
        screen.blit(cost_surf, (rect.x + 6, rect.y + NODE_H - 22))

    # Hint at bottom
    hint = _font(20).render(
        "Click a tech to research it  |  T or ESC = close",
        True, (120, 120, 150))
    screen.blit(hint, (PANEL_X + PANEL_W // 2 - hint.get_width() // 2,
                       PANEL_Y + PANEL_H - 30))


def handle_tech_screen_click(pos, civ, ui_state):
    """Returns True if the click was consumed by the tech screen."""
    if not ui_state.tech_screen_open:
        return False

    from civ_game.systems.tech_tree import can_research

    for tech_key in NODE_POSITIONS:
        rect = _node_rect(tech_key)
        if rect.collidepoint(pos):
            if can_research(tech_key, civ.techs_researched):
                civ.current_research = tech_key
            return True

    # Click outside panel closes the screen
    if not pygame.Rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H).collidepoint(pos):
        ui_state.tech_screen_open = False

    return True  # consume all clicks while open
