"""Illustrates state-management pattern: 08 Pygame Only.

Run from the repository root with `python examples/states/08_pygame_only.py`. See
`examples/states/README.md` for the state-example index."""

import pygame
from rix import GameStates

pygame.init()
screen = pygame.display.set_mode((640, 360))
clock = pygame.time.Clock()
screens = GameStates("menu")


@screens.screen("menu")
class Menu:
    def event(self, event: object) -> None:
        if getattr(event, "type", None) == pygame.KEYDOWN:
            screens.change("playing")

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("navy")


@screens.screen("playing")
class Playing:
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("darkgreen")


running = True
while running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        screens.event(event)
    screens.update(dt)
    screens.draw(screen)
    pygame.display.flip()
pygame.quit()
