"""Exercise Pygame-owned windowed/fullscreen transitions with attached bgfx."""

from __future__ import annotations

import pygame
import rix


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((640, 360), pygame.RESIZABLE)
    world = rix.World(screen, vsync=False)
    sizes: list[tuple[int, int]] = []
    handles: list[int] = []
    try:
        rix.Cube(world, color="orange", angular_velocity=(0, 45, 0))
        world.render()
        sizes.append(tuple(world.game._engine.viewport_size))
        handles.append(int(pygame.display.get_wm_info()["window"]))

        pygame.display.set_mode((640, 480), pygame.FULLSCREEN)
        world.render()
        sizes.append(tuple(world.game._engine.viewport_size))
        handles.append(int(pygame.display.get_wm_info()["window"]))

        pygame.display.set_mode((700, 420), pygame.RESIZABLE)
        world.render()
        sizes.append(tuple(world.game._engine.viewport_size))
        handles.append(int(pygame.display.get_wm_info()["window"]))

        assert sizes[0] == (640, 360)
        assert sizes[1][0] > 0 and sizes[1][1] > 0
        assert sizes[2] == (700, 420)
        assert all(handle != 0 for handle in handles)
        print(
            "RIX_PYGAME_FULLSCREEN_PASS",
            f"sizes={sizes}",
            f"hwnd_changes={sum(a != b for a, b in zip(handles, handles[1:]))}",
        )
    finally:
        world.close()
        pygame.quit()


if __name__ == "__main__":
    main()
