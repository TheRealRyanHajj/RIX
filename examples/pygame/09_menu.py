"""A Pygame menu layered over a live RIX scene."""

# Usage: from the repository root, run:
#   python examples/pygame/09_menu.py

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 48)
overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
world = rix.World(screen)
rix.Cube(
    world,
    color="orange",
    scale=2,
    angular_velocity=(0, 25, 0),
    collider=False,
)
world.set_overlay(overlay)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    overlay.fill((0, 0, 0, 100))
    pygame.draw.rect(overlay, (25, 35, 55, 235), (300, 150, 360, 220), border_radius=18)
    overlay.blit(font.render("RIX + Pygame", True, "white"), (340, 190))
    pygame.draw.rect(overlay, "orange", (370, 280, 220, 52), border_radius=10)
    overlay.blit(pygame.font.Font(None, 34).render("PLAY", True, "black"), (445, 293))
    world.overlay.update(overlay)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
