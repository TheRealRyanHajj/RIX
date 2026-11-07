"""Actual D3D11 validation for independent, buffered Pygame Viewports.

Run from the repository root on a visible Windows desktop:

    .venv\Scripts\python.exe tests\manual\pygame_viewport_gpu.py
"""

from __future__ import annotations

import hashlib

import pygame

import rix


def digest(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()[:16]


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((480, 270), pygame.RESIZABLE)
    world = rix.World(screen, mode="gpu", vsync=False)
    try:
        rix.Cube(world, position=(-1.25, 0, 0), color="orange")
        rix.Sphere(world, position=(1.1, 0.3, -0.8), radius=0.8, color="blue")
        rix.Plane(world, position=(0, -0.75, 0), size=12, color="gray")

        front_camera = rix.Camera(position=(0, 2.5, 6)).look_at((0, 0, 0))
        side_camera = rix.Camera(position=(6, 2.5, 0)).look_at((0, 0, 0))
        front = rix.Viewport(world, size=(192, 128), camera=front_camera)
        side = rix.Viewport(world, size=(128, 192), camera=side_camera)
        try:
            front_image = front.to_surface(blocking=True)
            side_image = side.to_surface(blocking=True)
            assert front_image.get_size() == (192, 128)
            assert side_image.get_size() == (128, 192)
            front_bytes = pygame.image.tobytes(front_image, "RGBA")
            side_bytes = pygame.image.tobytes(side_image, "RGBA")
            assert len(set(front_bytes)) > 8
            assert len(set(side_bytes)) > 8
            assert digest(front_image) != digest(
                pygame.transform.smoothscale(side_image, front_image.get_size())
            )

            previous = front.to_surface(refresh=False)
            front.refresh(blocking=False)
            buffered_completed = False
            for _ in range(8):
                current = front.refresh(blocking=False)
                if current is not previous:
                    buffered_completed = True
                    break
            assert buffered_completed, (
                "standalone buffered readback did not complete after eight polls"
            )
            print(
                "RIX_VIEWPORT_GPU_PASS",
                f"front={digest(front_image)}",
                f"side={digest(side_image)}",
                "buffered=true",
            )
        finally:
            front.close()
            side.close()
    finally:
        world.close()
        pygame.quit()


if __name__ == "__main__":
    main()
