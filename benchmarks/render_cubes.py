"""Repeatable native-renderer cube benchmark for Phase 1.9/1.10 validation."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import threading
import time
from dataclasses import asdict
from statistics import median

from easy3d import Camera, Cube, Game, Light, Scene


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("page_fault_count", ctypes.c_ulong),
        ("peak_working_set_size", ctypes.c_size_t),
        ("working_set_size", ctypes.c_size_t),
        ("quota_peak_paged_pool_usage", ctypes.c_size_t),
        ("quota_paged_pool_usage", ctypes.c_size_t),
        ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
        ("quota_non_paged_pool_usage", ctypes.c_size_t),
        ("pagefile_usage", ctypes.c_size_t),
        ("peak_pagefile_usage", ctypes.c_size_t),
        ("private_usage", ctypes.c_size_t),
    ]


def _memory_bytes() -> tuple[int, int, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCountersEx),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = _ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return (
        int(counters.working_set_size),
        int(counters.peak_working_set_size),
        int(counters.private_usage),
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((len(ordered) - 1) * fraction), len(ordered) - 1)
    return ordered[index]


def run(*, count: int, seconds: float) -> dict[str, object]:
    scene = Scene(f"{count} shared cubes")
    side = math.ceil(math.sqrt(count))
    extent = max((side - 1) * 2.0, 1.0)
    camera = Camera(
        position=(0, max(35.0, extent * 0.42), max(60.0, extent * 0.68)),
        vertical_fov_degrees=58,
        far_plane=max(1000.0, extent * 5.0),
    ).look_at((0, 0, 0))
    scene.camera = camera

    memory_before = _memory_bytes()
    creation_start = time.perf_counter()
    with scene:
        Light("ambient", intensity=0.22)
        Light("directional", intensity=0.9, rotation=(-45, -30, 0))
        for index in range(count):
            row, column = divmod(index, side)
            Cube(
                position=(
                    column * 2.0 - extent * 0.5,
                    0.0,
                    row * 2.0 - extent * 0.5,
                ),
                color=(0.22, 0.68, 0.95),
            )
    creation_seconds = time.perf_counter() - creation_start
    memory_after_creation = _memory_bytes()

    game = Game(
        f"Easy3D renderer benchmark — {count} cubes",
        (1280, 720),
        vsync=False,
    )
    game.load_scene(scene)
    frame_samples: list[float] = []
    latest_stats = game.renderer_stats

    def sample_and_stop() -> None:
        nonlocal latest_stats
        while not game.is_running:
            time.sleep(0.001)
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline and game.is_running:
            frame_seconds = game.last_frame_seconds
            if frame_seconds > 0:
                frame_samples.append(frame_seconds)
            latest_stats = game.renderer_stats
            time.sleep(0.01)
        game.stop()

    sampler = threading.Thread(target=sample_and_stop, daemon=True)
    sampler.start()
    run_start = time.perf_counter()
    game.run()
    run_seconds = time.perf_counter() - run_start
    sampler.join(timeout=1)
    latest_stats = game.renderer_stats
    memory_after_run = _memory_bytes()

    accounted = latest_stats.visible_instances + latest_stats.culled_instances
    if accounted != count:
        raise RuntimeError(
            f"renderer accounted for {accounted} instances, expected {count}"
        )
    if latest_stats.visible_instances > 1 and latest_stats.instanced_draw_calls == 0:
        raise RuntimeError("visible shared cubes were not submitted through instancing")

    frame_milliseconds = [sample * 1000.0 for sample in frame_samples]
    return {
        "requested_instances": count,
        "creation_seconds": creation_seconds,
        "run_seconds": run_seconds,
        "frames": game.frame_count,
        "overall_fps": game.frame_count / run_seconds if run_seconds else 0.0,
        "sample_count": len(frame_milliseconds),
        "frame_ms_median": median(frame_milliseconds) if frame_milliseconds else 0.0,
        "frame_ms_p95": _percentile(frame_milliseconds, 0.95),
        "frame_ms_p99": _percentile(frame_milliseconds, 0.99),
        "renderer": asdict(latest_stats),
        "memory": {
            "working_set_before": memory_before[0],
            "working_set_after_creation": memory_after_creation[0],
            "working_set_after_run": memory_after_run[0],
            "peak_working_set_after_run": memory_after_run[1],
            "private_bytes_after_run": memory_after_run[2],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    if arguments.count <= 0:
        parser.error("--count must be positive")
    if not math.isfinite(arguments.seconds) or arguments.seconds <= 0:
        parser.error("--seconds must be finite and positive")
    print(json.dumps(run(count=arguments.count, seconds=arguments.seconds), indent=2))


if __name__ == "__main__":
    main()
