"""Read 3D into a Pygame inventory panel (slower compatibility mode)."""

# Usage: from the repository root, run:
#   python examples/pygame/07_inventory_viewport.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((900, 600), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen, mode="surface")
item = rix.Cube(
    world,
    color="orange",
    scale=2,
    angular_velocity=(0, 45, 0),
    collider=False,
)
preview_camera = rix.Camera(position=(3.5, 2.5, 5)).look_at((0, 0, 0))
viewport = rix.Viewport(
    world,
    rect=pygame.Rect(60, 70, 320, 320),
    camera=preview_camera,
)

while world.running:
    dt = clock.tick(30) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    preview = viewport.to_surface()
    screen.fill((20, 24, 34))
    pygame.draw.rect(screen, (70, 78, 96), viewport.rect.inflate(12, 12), border_radius=10)
    screen.blit(preview, viewport.rect)
    pygame.display.flip()

viewport.close()
world.close()
pygame.quit()
