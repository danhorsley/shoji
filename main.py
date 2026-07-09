import sys

import pygame

from game import Game


def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 640))
    pygame.display.set_caption("Shoji - Entangled Doors Puzzle")
    clock = pygame.time.Clock()

    game = Game(screen)
    game.load_or_generate_level(0)

    def fit_window():
        w, h = game.preferred_window_size()
        pygame.display.set_mode((w, h))
        game.screen = pygame.display.get_surface()

    fit_window()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                game.handle_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    game.load_or_generate_level(game.current_level)
                    fit_window()
                elif event.key == pygame.K_n:
                    game.next_level()
                    fit_window()
                elif event.key == pygame.K_c:
                    game.curate_save()
                elif event.key == pygame.K_g:
                    # Hunt for a non-trivial puzzle and auto-curate it
                    game.hunt_curated(max_tries=80)
                    fit_window()
                elif event.key in (pygame.K_UP, pygame.K_w):
                    game.handle_move(0, -1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    game.handle_move(0, 1)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    game.handle_move(-1, 0)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    game.handle_move(1, 0)

        prev_level = game.current_level
        game.update()
        if game.current_level != prev_level:
            fit_window()
        game.draw()
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
