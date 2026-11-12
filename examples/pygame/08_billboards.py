"""Pygame images used as camera-facing world sprites."""

# Usage: from the repository root, run:
#   python examples/pygame/08_billboards.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
tree = pygame.Surface((96, 160), pygame.SRCALPHA)
pygame.draw.rect(tree, "saddlebrown", (40, 80, 16, 80))
pygame.draw.circle(tree, "forestgreen", (48, 60), 48)
world = rix.World(screen)
rix.Plane(world, size=40, color=(0.2, 0.4, 0.2))
for x in (-4, 0, 4):
    rix.Billboard(world, image=tree, position=(x, 2, -5), scale=4, axis="y")

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
