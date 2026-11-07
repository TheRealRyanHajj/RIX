"""First-person controller driven by forwarded Pygame events."""

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
clock = pygame.time.Clock()
world = rix.World(screen, graphics_preset="ultra")
rix.Plane(world, size=60, color=(0.22, 0.35, 0.2), collider=True)
for x in range(-3, 4):
    rix.Cube(world, position=(x * 2, 0.5, -4), color="orange", collider=True)
rix.Player(world, position=(0, 0.1, 4), controller="first_person")

while world.running:
    dt = clock.tick(240) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
