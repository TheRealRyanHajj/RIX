"""Use a Pygame Surface as a native GPU texture."""

# Usage: from the repository root, run:
#   python examples/pygame/05_surface_texture.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
art = pygame.Surface((128, 128), pygame.SRCALPHA)
art.fill("royalblue")
pygame.draw.circle(art, "gold", (64, 64), 42)
world = rix.World(screen)
rix.Cube(
    world,
    texture=art,
    scale=2.2,
    angular_velocity=(20, 35, 0),
    collider=False,
)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
