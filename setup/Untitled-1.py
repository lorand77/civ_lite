import pygame

pygame.init()

screen = pygame.display.set_mode((640, 480))
pygame.display.set_caption("Hello Pygame")

font = pygame.font.Font(None, 64)
text = font.render("Hello Pygame!", True, (255, 255, 0))

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((30, 30, 60))
    screen.blit(text, text.get_rect(center=(320, 240)))
    pygame.display.flip()

pygame.quit()
