"""Tiny hybrid game: Pygame score/HUD over moving RIX targets."""

# Usage: from the repository root, run:
#   python examples/pygame/14_hybrid_minigame.py

import random

import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 38)
overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
world = rix.World(screen)
target = rix.Sphere(world, radius=0.8, color="orange")
world.set_overlay(overlay)
score = 0

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            score += 1
            target.position = (random.uniform(-3, 3), random.uniform(-2, 2), 0)
    overlay.fill((0, 0, 0, 0))
    overlay.blit(font.render(f"Score: {score}", True, "white"), (24, 20))
    world.overlay.update(overlay)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
