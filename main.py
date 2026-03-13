import pygame
from civ_game.game import Game
from civ_game.ui.renderer import render
from civ_game.ui.hud import UIState, END_TURN_RECT
from civ_game.map.hex_grid import pixel_to_hex


def handle_event(event, game, ui_state):
    camera = game.camera

    if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:  # left click
            # Check END TURN button
            if END_TURN_RECT.collidepoint(event.pos):
                game.end_turn()
                return
            # Click on map → select tile
            hs = camera.effective_hex_size()
            q, r = pixel_to_hex(event.pos[0], event.pos[1],
                                 camera.offset_x, camera.offset_y, hs)
            tile = game.tiles.get((q, r))
            ui_state.selected_tile = tile

        elif event.button == 3:  # right click → deselect
            ui_state.deselect()

        elif event.button == 2:  # middle click → start pan drag
            ui_state.pan_start = event.pos

        elif event.button == 4:  # scroll up → zoom in
            camera.zoom = 1

        elif event.button == 5:  # scroll down → zoom out
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
        if event.key == pygame.K_RETURN:
            game.end_turn()


def main():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("CivPy")
    clock = pygame.time.Clock()

    game = Game(num_players=4, map_cols=32, map_rows=20, seed=42)
    ui_state = UIState()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue
            handle_event(event, game, ui_state)

        # Arrow key pan (continuous while held)
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
