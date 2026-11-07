"""Repeated Pygame HWND/bgfx initialization, rendering, resize, and shutdown."""

from __future__ import annotations

import pygame
import rix


def main() -> None:
    handles: list[int] = []
    for cycle in range(5):
        pygame.init()
        screen = pygame.display.set_mode((360 + cycle * 8, 240 + cycle * 6), pygame.RESIZABLE)
        world = rix.World(screen, vsync=False)
        try:
            rix.Cube(world, color="orange", angular_velocity=(0, 45, 0))
            first_handle = int(pygame.display.get_wm_info()["window"])
            handles.append(first_handle)
            for _ in range(3):
                world.update(1 / 60)
                world.render()
            resized = pygame.display.set_mode(
                (420 + cycle * 8, 280 + cycle * 6), pygame.RESIZABLE
            )
            assert resized is pygame.display.get_surface()
            world.render()
            assert world.game._engine.viewport_size == resized.get_size()
            assert int(pygame.display.get_wm_info()["window"]) != 0
        finally:
            world.close()
            pygame.quit()
    print("RIX_PYGAME_LIFECYCLE_PASS", f"cycles={len(handles)}")


if __name__ == "__main__":
    main()
