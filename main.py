import pygame
from civ_game.game import Game
from civ_game.ui.renderer import render
from civ_game.ui.hud import UIState, END_TURN_RECT
from civ_game.ui.city_screen import handle_city_screen_click
from civ_game.map.hex_grid import pixel_to_hex
from civ_game.entities.unit import get_reachable_tiles


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
            camera.zoom = 1

        elif event.button == 5:
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


def _handle_left_click(pos, game, ui_state):
    # City screen consumes its own clicks
    if ui_state.city_screen_open:
        handle_city_screen_click(pos, ui_state, game)
        return

    # END TURN button
    if END_TURN_RECT.collidepoint(pos):
        game.end_turn()
        ui_state.deselect()
        return

    camera = game.camera
    hs = camera.effective_hex_size()
    q, r = pixel_to_hex(pos[0], pos[1], camera.offset_x, camera.offset_y, hs)
    tile = game.tiles.get((q, r))
    if not tile:
        return

    civ = game.current_civ()
    selected_unit = ui_state.selected_unit

    # Move selected unit to reachable tile
    if selected_unit and (q, r) in ui_state.reachable_tiles:
        game.move_unit(selected_unit, q, r)
        ui_state.reachable_tiles = set()
        # Keep unit selected, recalculate reachable
        if selected_unit.moves_left > 0:
            ui_state.reachable_tiles = get_reachable_tiles(selected_unit, game.tiles)
        else:
            ui_state.selected_unit = None
        return

    # Click on a tile with a unit belonging to current player
    unit = tile.unit or tile.civilian
    if unit and unit.owner == game.current_player:
        ui_state.selected_unit = unit
        ui_state.selected_tile = None
        ui_state.selected_city = None
        ui_state.reachable_tiles = (
            get_reachable_tiles(unit, game.tiles) if unit.moves_left > 0 else set()
        )
        return

    # Click on a city tile
    if tile.city and tile.city.owner == game.current_player:
        ui_state.selected_city = tile.city
        ui_state.selected_unit = None
        ui_state.selected_tile = None
        ui_state.reachable_tiles = set()
        return

    # Plain tile select
    ui_state.selected_tile = tile
    ui_state.selected_unit = None
    ui_state.selected_city = None
    ui_state.reachable_tiles = set()


def _handle_key(key, game, ui_state):
    unit = ui_state.selected_unit
    civ = game.current_civ()

    if key == pygame.K_RETURN:
        game.end_turn()
        ui_state.deselect()

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

    elif key == pygame.K_ESCAPE:
        if ui_state.city_screen_open:
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
        ui_state.reachable_tiles = set()

    elif key == pygame.K_a and unit and unit.unit_type == "worker":
        game.start_improvement(unit, "farm")
        ui_state.reachable_tiles = set()

    elif key == pygame.K_p and unit and unit.unit_type == "worker":
        game.start_improvement(unit, "pasture")
        ui_state.reachable_tiles = set()


def main():
    pygame.init()
    screen = pygame.display.set_mode((1850, 1000))
    pygame.display.set_caption("CivPy")
    clock = pygame.time.Clock()

    game = Game(num_players=4, map_cols=32, map_rows=20, seed=None)
    ui_state = UIState()

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
