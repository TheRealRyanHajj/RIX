"""Validate fixed physics and character input under Pygame-supplied timing."""

from __future__ import annotations

import pygame
import rix


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((480, 270), pygame.RESIZABLE)
    world = rix.World(screen, fixed_hz=60, vsync=False)
    try:
        rix.Plane(world, size=30, collider=True, color="gray")
        ball = rix.Sphere(
            world,
            position=(2, 5, 0),
            radius=0.5,
            physics=True,
            color="orange",
        )
        player = rix.Player(world, position=(0, 0.1, 4), controller="first_person")

        starting_ball_y = ball.y
        for _ in range(90):
            world.update(1 / 60)
        assert ball.y < starting_ball_y - 1.0
        assert ball.y > -0.25

        starting_player = rix.Vec3(player.position)
        world.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
        for _ in range(45):
            world.update(1 / 60)
        world.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_w))
        world.update(1 / 60)
        assert (player.position - starting_player).length > 0.5

        grounded_y = player.y
        world.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        world.update(1 / 60)
        world.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE))
        for _ in range(8):
            world.update(1 / 60)
        assert player.y > grounded_y + 0.05
        world.render()
        print(
            "RIX_PYGAME_PHYSICS_PASS",
            f"ball_y={ball.y:.3f}",
            f"player_distance={(player.position - starting_player).length:.3f}",
            f"jump_delta={player.y - grounded_y:.3f}",
        )
    finally:
        world.close()
        pygame.quit()


if __name__ == "__main__":
    main()
