"""Measure Pygame HWND presentation, Surface readback, and Surface uploads."""

# Usage: from the repository root, run:
#   python benchmarks/pygame_integration.py
# This prints benchmark measurements.

from __future__ import annotations

import argparse
import ctypes
import statistics
import time

import pygame
import rix


def process_memory() -> tuple[int, int]:
    """Return Windows working-set/private bytes without another dependency."""

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCountersEx),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    ):
        return 0, 0
    return int(counters.WorkingSetSize), int(counters.PrivateUsage)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("gpu", "surface", "viewport"), default="gpu")
    parser.add_argument("--objects", type=int, default=100)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--size", type=int, nargs=2, default=(960, 540))
    parser.add_argument("--viewport-size", type=int, nargs=2, default=(256, 256))
    parser.add_argument("--physics-bodies", type=int, default=0)
    parser.add_argument("--overlay", action="store_true")
    args = parser.parse_args()
    if args.objects < 0 or args.frames <= 0 or args.physics_bodies < 0:
        parser.error("object counts must be non-negative and frames must be positive")

    pygame.init()
    screen = pygame.display.set_mode(tuple(args.size), pygame.RESIZABLE)
    world = rix.World(
        screen,
        mode="surface" if args.mode in ("surface", "viewport") else "gpu",
        vsync=False,
        graphics_preset="medium",
    )
    columns = max(1, int(args.objects**0.5))
    for index in range(args.objects):
        x = (index % columns) - columns * 0.5
        z = -(index // columns) * 1.3
        rix.Cube(world, position=(x * 1.3, 0, z), color="orange")

    if args.physics_bodies:
        rix.Plane(world, y=-1, size=100, collider=True, color="gray")
        physics_columns = max(1, int(args.physics_bodies**0.5))
        for index in range(args.physics_bodies):
            x = (index % physics_columns) - physics_columns * 0.5
            y = 1 + index // physics_columns * 1.1
            rix.Sphere(
                world,
                position=(x * 1.1, y, 0),
                radius=0.45,
                physics=True,
                color="blue",
            )

    overlay = None
    if args.overlay and args.mode == "gpu":
        overlay = pygame.Surface(tuple(args.size), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (20, 40, 80, 180), (10, 10, 260, 60))
        overlay.blit(pygame.font.Font(None, 32).render("Pygame overlay", True, "white"), (24, 26))
        world.set_overlay(overlay)

    upload_surface = pygame.Surface((512, 512), pygame.SRCALPHA)
    upload_texture = rix.SurfaceTexture(upload_surface)
    upload_ms: list[float] = []
    frame_ms: list[float] = []
    update_ms: list[float] = []
    viewport = None
    if args.mode == "viewport":
        camera = rix.Camera(position=(0, 4, 9)).look_at((0, 0, -4))
        viewport = rix.Viewport(
            world,
            size=tuple(args.viewport_size),
            camera=camera,
        )
    for frame in range(args.frames + 5):
        update_start = time.perf_counter()
        world.update(1 / 60)
        update_elapsed = (time.perf_counter() - update_start) * 1000
        if overlay is not None:
            overlay.set_at((frame % overlay.get_width(), 0), (255, 255, 255, 255))
            world.overlay.update(overlay)
        if frame >= 5:
            upload_start = time.perf_counter()
            upload_texture.update(upload_surface)
            upload_ms.append((time.perf_counter() - upload_start) * 1000)
        start = time.perf_counter()
        image = (
            viewport.refresh(blocking=True)
            if viewport is not None
            else world.render()
        )
        if args.mode == "surface":
            screen.blit(image, (0, 0))
            pygame.display.flip()
        elapsed = (time.perf_counter() - start) * 1000
        if frame >= 5:
            frame_ms.append(elapsed)
            update_ms.append(update_elapsed)

    stats = world.renderer_stats
    working_set, private_bytes = process_memory()
    print(
        f"mode={args.mode} objects={args.objects} frames={args.frames} "
        f"size={args.size[0]}x{args.size[1]} "
        f"viewport={args.viewport_size[0]}x{args.viewport_size[1]} "
        f"physics_bodies={args.physics_bodies} "
        f"mean_ms={statistics.mean(frame_ms):.3f} "
        f"p95_ms={sorted(frame_ms)[int(len(frame_ms) * 0.95) - 1]:.3f} "
        f"fps={1000 / statistics.mean(frame_ms):.1f} "
        f"update_mean_ms={statistics.mean(update_ms):.3f} "
        f"update_p95_ms={sorted(update_ms)[int(len(update_ms) * 0.95) - 1]:.3f} "
        f"upload_512_ms={statistics.mean(upload_ms):.3f} "
        f"cpu_ms={stats.cpu_frame_ms:.3f} gpu_ms={stats.gpu_frame_ms:.3f} "
        f"draw_calls={stats.draw_calls} visible={stats.visible_instances} "
        f"instanced={stats.instanced_draw_calls} texture_bytes={stats.texture_memory_bytes} "
        f"working_set={working_set} private_bytes={private_bytes}"
    )
    if viewport is not None:
        viewport.close()
    world.close()
    pygame.quit()


if __name__ == "__main__":
    main()
