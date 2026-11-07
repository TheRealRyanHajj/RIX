"""Visible decision-gate test for attaching bgfx to a Pygame CE SDL2 HWND.

This is intentionally a manual prototype, not a supported public API example.
RIX must remain the only presenter while attached: do not call display.flip().
"""

from __future__ import annotations

import argparse
import time

import pygame

from rix import Cube, Game


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=180)
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames must be positive")
    pygame.init()
    flags = pygame.RESIZABLE
    screen = pygame.display.set_mode((640, 360), flags)
    pygame.display.set_caption("RIX Pygame HWND decision gate")
    info = pygame.display.get_wm_info()
    hwnd = int(info.get("window", 0))
    if hwnd == 0:
        raise RuntimeError(f"Pygame did not expose a Win32 HWND: {info!r}")

    game = Game("External prototype", resolution=screen.get_size(), vsync=False)
    Cube(position=(0.0, 0.0, -4.0), color="orange")
    game.camera.position = (0.0, 1.5, 3.0)
    game.camera.look_at((0.0, 0.0, -4.0))

    game._engine.begin_external_window(hwnd, *screen.get_size())
    try:
        for frame in range(args.frames):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
            if frame == 60:
                screen = pygame.display.set_mode((800, 450), flags)
                resized_hwnd = int(pygame.display.get_wm_info().get("window", 0))
                if resized_hwnd != hwnd:
                    raise RuntimeError(
                        "Pygame replaced its HWND during resize; external swap-chain "
                        "reattachment is required"
                    )
                game._engine.resize_external_window(*screen.get_size())
            game._engine.render_external_window()
            time.sleep(1.0 / 120.0)
        stats = game.renderer_stats
        print(
            "PYGAME_HWND_PROTOTYPE_PASS",
            pygame.version.ver,
            pygame.get_sdl_version(),
            hwnd,
            game._engine.frame_count,
            stats.draw_calls,
            game._engine.viewport_size,
        )
    finally:
        game._engine.end_external_window()
        game.close()
        pygame.display.quit()
        pygame.quit()


if __name__ == "__main__":
    main()
