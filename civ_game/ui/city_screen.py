import pygame
from civ_game.data.units import UNIT_DEFS
from civ_game.data.buildings import BUILDING_DEFS
from civ_game.systems.yields import compute_city_yields

SCREEN_W = 1850
SCREEN_H = 1000
HUD_HEIGHT = 180

MODAL_W = 720
MODAL_H = 580
MODAL_X = (SCREEN_W - MODAL_W) // 2
MODAL_Y = (SCREEN_H - HUD_HEIGHT - MODAL_H) // 2

COLOR_BG      = (25, 25, 35)
COLOR_BORDER  = (120, 120, 160)
COLOR_HEADER  = (45, 45, 60)
COLOR_TEXT    = (230, 230, 230)
COLOR_DIM     = (150, 150, 150)
COLOR_BUILD   = (50, 80, 50)
COLOR_BUILD_H = (70, 110, 70)
COLOR_CLOSE   = (90, 40, 40)
COLOR_CLOSE_H = (130, 60, 60)

_font_cache: dict = {}

def _font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.Font(None, size)
    return _font_cache[size]


def render_city_screen(screen, city, civ, ui_state):
    """Draw the city modal. Stores clickable rects into ui_state."""
    mx, my = MODAL_X, MODAL_Y

    # Dim background
    dim = pygame.Surface((SCREEN_W, SCREEN_H - HUD_HEIGHT), pygame.SRCALPHA)
    dim.fill((0, 0, 0, 160))
    screen.blit(dim, (0, 0))

    # Modal background
    pygame.draw.rect(screen, COLOR_BG, (mx, my, MODAL_W, MODAL_H))
    pygame.draw.rect(screen, COLOR_BORDER, (mx, my, MODAL_W, MODAL_H), 2)

    # Header
    pygame.draw.rect(screen, COLOR_HEADER, (mx, my, MODAL_W, 34))
    title = _font(27).render(f"{city.name}  (Pop: {city.population})", True, COLOR_TEXT)
    screen.blit(title, (mx + 12, my + 8))

    y = my + 54
    lx = mx + 14
    line_h = 30

    yields = compute_city_yields(city, _city_screen_tiles, civ)

    # Yields row
    y_str = (f"Yields:  Food {yields['food']}  Prod {yields['prod']}  "
             f"Gold {yields['gold']}  Sci {yields['science']}  Cult {yields['culture']}")
    screen.blit(_font(21).render(y_str, True, COLOR_TEXT), (lx, y)); y += line_h

    # Food progress
    threshold = city.food_growth_threshold
    turns_to_grow = "—"
    net = yields["food"] - city.population * 2
    if net > 0:
        turns_to_grow = max(1, (threshold - city.food_stored + net - 1) // net)
    food_str = (f"Food: {city.food_stored}/{threshold} stored  "
                f"(net {net:+d}/turn,  {turns_to_grow} turns to grow)")
    screen.blit(_font(21).render(food_str, True, COLOR_TEXT), (lx, y)); y += line_h + 8

    # Divider
    pygame.draw.line(screen, COLOR_BORDER, (mx + 8, y), (mx + MODAL_W - 8, y), 1)
    y += 8

    # Production section
    screen.blit(_font(23).render("Production", True, COLOR_TEXT), (lx, y)); y += line_h

    if city.production_queue:
        current_key = city.production_queue[0]
        cost = _item_cost(current_key)
        prod_per_turn = max(1, yields["prod"])
        remaining = cost - city.production_progress
        turns = max(1, (remaining + prod_per_turn - 1) // prod_per_turn)
        bar_w = MODAL_W - 28
        filled = int(bar_w * min(1.0, city.production_progress / cost))
        pygame.draw.rect(screen, (50, 50, 70), (lx, y, bar_w, 22))
        pygame.draw.rect(screen, (80, 140, 80), (lx, y, filled, 22))
        pygame.draw.rect(screen, COLOR_BORDER, (lx, y, bar_w, 22), 1)
        label = _item_name(current_key)
        bar_text = _font(20).render(f"{label}  {city.production_progress}/{cost}  ({turns} turns)", True, COLOR_TEXT)
        screen.blit(bar_text, (lx + 4, y + 2)); y += 30
    else:
        screen.blit(_font(21).render("Nothing queued", True, COLOR_DIM), (lx, y)); y += line_h

    y += 4
    pygame.draw.line(screen, COLOR_BORDER, (mx + 8, y), (mx + MODAL_W - 8, y), 1)
    y += 8

    # Buildings
    bld_names = ", ".join(BUILDING_DEFS[b]["name"] for b in city.buildings) or "None"
    screen.blit(_font(21).render(f"Buildings: {bld_names}", True, COLOR_DIM), (lx, y)); y += line_h + 4

    pygame.draw.line(screen, COLOR_BORDER, (mx + 8, y), (mx + MODAL_W - 8, y), 1)
    y += 8

    # Available to build
    screen.blit(_font(23).render("Build:", True, COLOR_TEXT), (lx, y)); y += line_h

    ui_state.city_screen_item_rects = []
    mouse = pygame.mouse.get_pos()

    # Show buildings not yet built (tech requirements met)
    for key, defn in BUILDING_DEFS.items():
        if key == "palace" or key in city.buildings:
            continue
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue
        if y + 28 > my + MODAL_H - 54:
            break
        cost = defn["prod_cost"]
        prod_pt = max(1, yields["prod"])
        turns = max(1, (cost + prod_pt - 1) // prod_pt)
        label = f"[{defn['name']}  —  {cost} prod  ({turns} turns)]"
        rect = pygame.Rect(lx, y, MODAL_W - 28, 28)
        color = COLOR_BUILD_H if rect.collidepoint(mouse) else COLOR_BUILD
        pygame.draw.rect(screen, color, rect, border_radius=3)
        screen.blit(_font(20).render(label, True, COLOR_TEXT), (lx + 4, y + 4))
        ui_state.city_screen_item_rects.append((rect, key))
        y += 32

    # Show all buildable units (tech and resource requirements met)
    for key, defn in UNIT_DEFS.items():
        if defn["type"] == "civilian" and key not in ("settler", "worker"):
            continue
        req_tech = defn.get("requires_tech")
        if req_tech and req_tech not in civ.techs_researched:
            continue
        req_res = defn.get("requires_resource")
        if req_res:
            # Check if civ has this resource connected (worked by any city)
            has_res = any(
                _city_screen_tiles.get((tq, tr)) and
                _city_screen_tiles[(tq, tr)].resource == req_res
                for c in [city]
                for tq, tr in c.worked_tiles
            )
            if not has_res:
                continue
        if y + 28 > my + MODAL_H - 54:
            break
        cost = defn["prod_cost"]
        prod_pt = max(1, yields["prod"])
        turns = max(1, (cost + prod_pt - 1) // prod_pt)
        label = f"[{defn['name']}  —  {cost} prod  ({turns} turns)]"
        rect = pygame.Rect(lx, y, MODAL_W - 28, 28)
        color = COLOR_BUILD_H if rect.collidepoint(mouse) else COLOR_BUILD
        pygame.draw.rect(screen, color, rect, border_radius=3)
        screen.blit(_font(20).render(label, True, COLOR_TEXT), (lx + 4, y + 4))
        ui_state.city_screen_item_rects.append((rect, key))
        y += 32

    # Close button
    close_rect = pygame.Rect(mx + MODAL_W - 120, my + MODAL_H - 46, 106, 36)
    color = COLOR_CLOSE_H if close_rect.collidepoint(mouse) else COLOR_CLOSE
    pygame.draw.rect(screen, color, close_rect, border_radius=3)
    pygame.draw.rect(screen, COLOR_BORDER, close_rect, 1, border_radius=3)
    close_surf = _font(21).render("CLOSE", True, COLOR_TEXT)
    screen.blit(close_surf, close_surf.get_rect(center=close_rect.center))
    ui_state.city_screen_close_rect = close_rect


# Module-level tile reference set by game before rendering
_city_screen_tiles = {}


def set_tiles(tiles):
    global _city_screen_tiles
    _city_screen_tiles = tiles


def _item_cost(key):
    if key in BUILDING_DEFS:
        return BUILDING_DEFS[key]["prod_cost"]
    if key in UNIT_DEFS:
        return UNIT_DEFS[key]["prod_cost"]
    return 9999


def _item_name(key):
    if key in BUILDING_DEFS:
        return BUILDING_DEFS[key]["name"]
    if key in UNIT_DEFS:
        return UNIT_DEFS[key]["name"]
    return key


def handle_city_screen_click(pos, ui_state, game):
    """Returns True if the click was consumed by the city screen."""
    if not ui_state.city_screen_open:
        return False

    # Close button
    if ui_state.city_screen_close_rect and ui_state.city_screen_close_rect.collidepoint(pos): # type: ignore
        ui_state.city_screen_open = False
        return True

    # Build item
    for rect, key in ui_state.city_screen_item_rects:
        if rect.collidepoint(pos):
            city = ui_state.selected_city
            if city:
                if key in city.production_queue:
                    city.production_queue.remove(key)
                city.production_queue.insert(0, key)
            return True

    # Click outside modal → close
    mx, my = MODAL_X, MODAL_Y
    if not pygame.Rect(mx, my, MODAL_W, MODAL_H).collidepoint(pos):
        ui_state.city_screen_open = False

    return True  # consume all clicks while screen is open
