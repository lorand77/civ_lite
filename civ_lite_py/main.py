import pygame
from civ_game.game import Game
from civ_game.ui.renderer import render, WIN_EXIT_RECT, compute_score
from civ_game.ui.hud import UIState, END_TURN_RECT
from civ_game.ui.city_screen import handle_city_screen_click, handle_city_screen_scroll
from civ_game.ui.tech_screen import handle_tech_screen_click
from civ_game.map.hex_grid import pixel_to_hex
from civ_game.entities.unit import get_reachable_tiles, get_attackable_tiles

CPU_TURN_DELAY_MS = 10  # milliseconds to pause after each CPU civ's turn


def handle_event(event, game, ui_state):
    camera = game.camera

    if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:
            _handle_left_click(event.pos, game, ui_state)

        elif event.button == 3:
            ui_state.deselect()

        elif event.button == 2:
            ui_state.pan_start = event.pos

        elif event.button == 4:
            if ui_state.city_screen_open:
                handle_city_screen_scroll(-1, ui_state)
            else:
                camera.zoom = 1

        elif event.button == 5:
            if ui_state.city_screen_open:
                handle_city_screen_scroll(1, ui_state)
            else:
                camera.zoom = 0

    elif event.type == pygame.MOUSEMOTION:
        if ui_state.pan_start:
            dx = event.pos[0] - ui_state.pan_start[0]
            dy = event.pos[1] - ui_state.pan_start[1]
            camera.pan(dx, dy)
            ui_state.pan_start = event.pos

    elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 2:
            ui_state.pan_start = None

    elif event.type == pygame.KEYDOWN:
        _handle_key(event.key, game, ui_state)


def _select_unit(unit, game, ui_state):
    """Select a unit and compute its move/attack sets."""
    ui_state.selected_unit = unit
    ui_state.selected_tile = None
    ui_state.selected_city = None
    if unit.moves_left > 0:
        ui_state.reachable_tiles = get_reachable_tiles(unit, game.tiles, game.turn)
        ui_state.attackable_tiles = get_attackable_tiles(unit, game.tiles)
    else:
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()


def _promote_queued_message(ui_state):
    """Promote a queued start-of-turn message and open tech screen if needed."""
    if ui_state.queued_message:
        ui_state.set_message(ui_state.queued_message)
        ui_state.queued_message = ""
    if ui_state.auto_open_tech:
        ui_state.tech_screen_open = True
        ui_state.auto_open_tech = False


def _run_cpu_turns(game, ui_state):
    """Run all consecutive CPU turns, panning the camera to each civ after its move."""
    from civ_game.map.hex_grid import hex_to_pixel, HEX_SIZE
    from civ_game.systems.ai import ai_take_turn

    while (game.winner is None
           and game.current_civ().is_cpu):
        cpu_civ = game.current_civ()
        ai_take_turn(game, cpu_civ)

        focus = cpu_civ.original_capital
        if not focus and cpu_civ.units:
            focus = cpu_civ.units[0]
        if focus:
            px, py = hex_to_pixel(focus.q, focus.r, hex_size=HEX_SIZE)
            game.camera.center_on_pixel(px, py)
        render(ui_state.screen, game, game.camera, ui_state)
        pygame.display.flip()

        if game.winner is not None:
            break

        pygame.time.wait(CPU_TURN_DELAY_MS)
        game.end_turn()
        _record_scores(game, ui_state)

    # Now current player is human (or game is won) — show turn banner
    ui_state.turn_banner_timer = 120

    new_civ = game.current_civ()
    from civ_game.map.hex_grid import hex_to_pixel, HEX_SIZE
    cap = new_civ.original_capital
    if cap:
        px, py = hex_to_pixel(cap.q, cap.r, hex_size=HEX_SIZE)
        game.camera.center_on_pixel(px, py)
    else:
        settler = next((u for u in new_civ.units if u.unit_type == "settler"), None)
        if settler:
            px, py = hex_to_pixel(settler.q, settler.r, hex_size=HEX_SIZE)
            game.camera.center_on_pixel(px, py)

    if new_civ.pending_messages:
        ui_state.queued_message = "\n".join(new_civ.pending_messages)
        new_civ.pending_messages.clear()
    if new_civ.research_just_completed:
        ui_state.auto_open_tech = True
        new_civ.research_just_completed = False


def _record_scores(game, ui_state):
    """Append one score snapshot per game turn (called whenever game.turn advances)."""
    if game.turn != ui_state._last_recorded_turn:
        ui_state.score_history.append([compute_score(c, game) for c in game.civs])
        ui_state._last_recorded_turn = game.turn


def _do_end_turn(game, ui_state):
    game.end_turn()
    _record_scores(game, ui_state)
    ui_state.deselect()
    _run_cpu_turns(game, ui_state)


def _handle_left_click(pos, game, ui_state):
    # Exit button on win screen
    if game.winner is not None:
        if WIN_EXIT_RECT.collidepoint(pos):
            pygame.quit()
            raise SystemExit
        return

    # Dismiss turn banner on click
    if ui_state.turn_banner_timer > 0:
        ui_state.turn_banner_timer = 0
        _promote_queued_message(ui_state)
        return

    # Tech screen consumes its own clicks
    if ui_state.tech_screen_open:
        handle_tech_screen_click(pos, game.current_civ(), ui_state)
        return

    # City screen consumes its own clicks
    if ui_state.city_screen_open:
        handle_city_screen_click(pos, ui_state, game)
        return

    # END TURN button
    if END_TURN_RECT.collidepoint(pos):
        _do_end_turn(game, ui_state)
        return

    camera = game.camera
    hs = camera.effective_hex_size()
    q, r = pixel_to_hex(pos[0], pos[1], camera.offset_x, camera.offset_y, hs)
    tile = game.tiles.get((q, r))
    if not tile:
        return

    selected_unit = ui_state.selected_unit

    # Attack selected: click on attackable tile
    if selected_unit and (q, r) in ui_state.attackable_tiles:
        msg = game.do_attack(selected_unit, q, r)
        if msg:
            ui_state.set_message(msg)
        ui_state.deselect()
        # Re-select attacker if still alive
        if selected_unit in game.civs[selected_unit.owner].units:
            _select_unit(selected_unit, game, ui_state)
        return

    # Move selected unit to reachable tile
    if selected_unit and (q, r) in ui_state.reachable_tiles:
        cost = ui_state.reachable_tiles[(q, r)]
        game.move_unit(selected_unit, q, r, cost=cost)
        # Recalculate after move
        if selected_unit.moves_left > 0:
            ui_state.reachable_tiles = get_reachable_tiles(selected_unit, game.tiles)
            ui_state.attackable_tiles = get_attackable_tiles(selected_unit, game.tiles)
        else:
            ui_state.reachable_tiles = {}
            ui_state.attackable_tiles = set()
            ui_state.selected_unit = None
        return

    # Click on a tile with a unit belonging to current player
    unit = tile.unit or tile.civilian
    if unit and unit.owner == game.current_player:
        _select_unit(unit, game, ui_state)
        return

    # Click on a city tile
    if tile.city and tile.city.owner == game.current_player:
        ui_state.selected_city = tile.city
        ui_state.selected_unit = None
        ui_state.selected_tile = None
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()
        return

    # Plain tile select
    ui_state.selected_tile = tile
    ui_state.selected_unit = None
    ui_state.selected_city = None
    ui_state.reachable_tiles = {}
    ui_state.attackable_tiles = set()


def _handle_key(key, game, ui_state):
    # Block input if game is won
    if game.winner is not None:
        return

    # Dismiss turn banner on any key press
    if ui_state.turn_banner_timer > 0:
        ui_state.turn_banner_timer = 0
        _promote_queued_message(ui_state)
        return

    unit = ui_state.selected_unit

    if key == pygame.K_RETURN:
        _do_end_turn(game, ui_state)

    elif key == pygame.K_t:
        ui_state.tech_screen_open = not ui_state.tech_screen_open
        ui_state.city_screen_open = False  # close city screen if open

    elif key == pygame.K_b:
        # Open city screen for selected city, or city on selected unit's tile
        city = ui_state.selected_city
        if not city and unit:
            tile = game.tiles.get((unit.q, unit.r))
            if tile and tile.city and tile.city.owner == game.current_player:
                city = tile.city
        if city:
            ui_state.selected_city = city
            ui_state.city_screen_open = True
            ui_state.city_screen_scroll = 0

    elif key == pygame.K_ESCAPE:
        if ui_state.tech_screen_open:
            ui_state.tech_screen_open = False
        elif ui_state.city_screen_open:
            ui_state.city_screen_open = False
        else:
            ui_state.deselect()

    elif key == pygame.K_f and unit and unit.unit_type == "settler":
        tile = game.tiles.get((unit.q, unit.r))
        if tile and tile.terrain != "ocean" and tile.city is None:
            city = game.found_city(unit)
            ui_state.deselect()
            ui_state.selected_city = city

    elif key == pygame.K_m and unit and unit.unit_type == "worker":
        game.start_improvement(unit, "mine")
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()

    elif key == pygame.K_a and unit and unit.unit_type == "worker":
        game.start_improvement(unit, "farm")
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()

    elif key == pygame.K_p and unit and unit.unit_type == "worker":
        game.start_improvement(unit, "pasture")
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()

    elif key == pygame.K_k and unit and not unit.is_civilian:
        # Fortify unit
        unit.fortified = True
        unit.healing = False
        unit.moves_left = 0
        ui_state.reachable_tiles = {}
        ui_state.attackable_tiles = set()

    elif key == pygame.K_h and unit and not unit.is_civilian:
        from civ_game.data.units import UNIT_DEFS as _UD
        # Heal: only allowed when unit has full movement points
        if unit.moves_left == _UD[unit.unit_type]["moves"]:
            unit.healing = True
            unit.fortified = False
            unit.fortify_bonus = 0.0
            unit.moves_left = 0
            ui_state.reachable_tiles = {}
            ui_state.attackable_tiles = set()

    elif key == pygame.K_u and unit and not unit.is_civilian:
        ok, msg = game.upgrade_unit(unit)
        if msg:
            ui_state.set_message(msg)
        if ok:
            ui_state.reachable_tiles = {}
            ui_state.attackable_tiles = set()


def main():
    pygame.init()
    screen = pygame.display.set_mode((1850, 1000))
    pygame.display.set_caption("CivPy")
    clock = pygame.time.Clock()

    from civ_game.ui.setup_screen import run_setup_screen
    cpu_flags = run_setup_screen(screen)
    game = Game(num_players=4, map_cols=32, map_rows=20, seed=None, cpu_flags=cpu_flags)
    ui_state = UIState(screen=screen)

    # Record turn 1 baseline scores
    _record_scores(game, ui_state)

    # If the starting player is CPU, kick off the AI loop immediately
    if game.current_civ().is_cpu:
        _run_cpu_turns(game, ui_state)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            handle_event(event, game, ui_state)

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:  game.camera.pan(-8, 0)
        if keys[pygame.K_RIGHT]: game.camera.pan(8, 0)
        if keys[pygame.K_UP]:    game.camera.pan(0, -8)
        if keys[pygame.K_DOWN]:  game.camera.pan(0, 8)

        render(screen, game, game.camera, ui_state)
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
    print("Game exited.")
