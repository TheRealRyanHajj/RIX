"""Jolt fixed-step physics under Pygame variable timing."""

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)
rix.Plane(world, size=30, color=(0.25, 0.3, 0.35), collider=True)
for y in range(1, 8):
    rix.Sphere(world, position=(0, y * 1.1, 0), color="orange", physics=True)

while world.running:
    dt = clock.tick(90) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
