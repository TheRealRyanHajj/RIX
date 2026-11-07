"""Render two independent RIX cameras into one Pygame application."""

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((1000, 600), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen, mode="surface")
rix.Cube(
    world,
    position=(-1.25, 0, 0),
    color="orange",
    angular_velocity=(15, 40, 0),
    collider=False,
)
rix.Sphere(world, position=(1.25, 0.2, -0.6), radius=0.8, color="blue")
rix.Plane(world, y=-0.75, size=14, color="gray")
front_camera = rix.Camera(position=(0, 3, 7)).look_at((0, 0, 0))
side_camera = rix.Camera(position=(7, 3, 0)).look_at((0, 0, 0))
large = rix.Viewport(
    world,
    rect=pygame.Rect(40, 60, 560, 480),
    camera=front_camera,
)
small = rix.Viewport(
    world,
    rect=pygame.Rect(650, 170, 280, 240),
    camera=side_camera,
)

while world.running:
    dt = clock.tick(30) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    front = large.to_surface()
    side = small.to_surface()
    screen.fill((18, 21, 29))
    screen.blit(front, large.rect)
    screen.blit(side, small.rect)
    pygame.display.flip()

large.close()
small.close()
world.close()
pygame.quit()
