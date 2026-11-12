"""Explicitly update a changing Pygame Surface texture."""

# Usage: from the repository root, run:
#   python examples/pygame/06_dynamic_surface.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
canvas = pygame.Surface((128, 128), pygame.SRCALPHA)
world = rix.World(screen)
cube = rix.Cube(
    world,
    texture=canvas,
    scale=2.2,
    angular_velocity=(0, 30, 0),
    collider=False,
)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    canvas.fill("midnightblue")
    x = int((pygame.time.get_ticks() * 0.08) % 128)
    pygame.draw.circle(canvas, "tomato", (x, 64), 18)
    cube.texture.update(canvas)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
