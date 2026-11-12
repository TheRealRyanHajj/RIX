"""Pygame owns the window and loop; RIX owns direct 3D presentation."""

# Usage: from the repository root, run:
#   python examples/pygame/01_cube.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
clock = pygame.time.Clock()
world = rix.World(screen)
rix.Cube(
    world,
    color="#6677dd",
    scale=2,
    angular_acceleration=(20, 20, 0),
    collider=False,
)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
        if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        world.stop()
    world.update(dt)
    world.render()  # RIX presents; no pygame.display.flip() in GPU mode.

world.close()
pygame.quit()
