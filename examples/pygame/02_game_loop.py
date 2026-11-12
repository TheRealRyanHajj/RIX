"""Use ordinary Pygame state to control a RIX entity."""

# Usage: from the repository root, run:
#   python examples/pygame/02_game_loop.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)
cube = rix.Cube(world, color="skyblue", scale=1.5, collider=False)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    keys = pygame.key.get_pressed()
    cube.position.x += (keys[pygame.K_d] - keys[pygame.K_a]) * 3 * dt
    cube.position.y += (keys[pygame.K_w] - keys[pygame.K_s]) * 3 * dt
    world.update(dt)
    world.render()

world.close()
pygame.quit()
