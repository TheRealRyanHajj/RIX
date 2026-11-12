"""Pygame fonts and drawing composited over direct RIX 3D."""

# Usage: from the repository root, run:
#   python examples/pygame/04_overlay.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 42)
overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
world = rix.World(screen)
rix.Sphere(
    world,
    radius=1.4,
    color="orange",
    angular_velocity=(0, 35, 0),
    collider=False,
)
world.set_overlay(overlay)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    overlay.fill((0, 0, 0, 0))
    overlay.blit(font.render(f"Pygame UI  {clock.get_fps():.0f} FPS", True, "white"), (24, 20))
    pygame.draw.rect(overlay, (30, 120, 220, 190), (20, 66, 240, 18), border_radius=9)
    world.overlay.update(overlay)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
