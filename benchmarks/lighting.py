"""Repeatable D3D11 benchmark for bounded multi-light selection and shading."""

# Usage: from the repository root, run:
#   python benchmarks/lighting.py
# This prints benchmark measurements.

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from dataclasses import asdict
from typing import Literal

from rix import Camera, Cube, Game, Light, Plane, Scene


def run(
    *,
    directional_lights: int,
    point_lights: int,
    spot_lights: int,
    seconds: float,
    preset: Literal["low", "medium", "high", "ultra"],
) -> dict[str, object]:
    scene = Scene("lighting benchmark")
    scene.camera = Camera(position=(20, 15, 24), far_plane=300).look_at((0, 0, 0))
    with scene:
        Light("ambient", intensity=0.12)
        for index in range(directional_lights):
            Light("directional", intensity=0.28, rotation=(-45, index * 90, 0))
        for index in range(point_lights):
            angle = index * math.tau / max(point_lights, 1)
            Light(
                "point", position=(math.cos(angle) * 12, 3, math.sin(angle) * 12),
                color=(0.5 + 0.5 * math.sin(angle),
                       0.5 + 0.5 * math.sin(angle + 2.1),
                       0.5 + 0.5 * math.sin(angle + 4.2)),
                intensity=8, range=10,
            )
        for index in range(spot_lights):
            angle = index * math.tau / max(spot_lights, 1)
            light = Light(
                "spot", position=(math.cos(angle) * 15, 9, math.sin(angle) * 15),
                intensity=10, range=24, inner_angle=24, angle=48,
            )
            light.look_at((0, 0, 0))
        Plane(size=(36, 36), color="gray")
        for z in range(-5, 6):
            for x in range(-5, 6):
                Cube(position=(x * 2.2, 0.6, z * 2.2), size=1.2,
                     color=(0.7, 0.55, 0.4))

    game = Game(
        "RIX lighting benchmark", (1280, 720), vsync=False,
        graphics_preset=preset, auto_setup=False,
    )
    game.load_scene(scene)
    threading.Thread(
        target=lambda: (time.sleep(seconds), game.stop()), daemon=True
    ).start()
    started = time.perf_counter()
    game.run()
    elapsed = time.perf_counter() - started
    stats = game.renderer_stats
    return {
        "requested_directional_lights": directional_lights,
        "requested_point_lights": point_lights,
        "requested_spot_lights": spot_lights,
        "seconds": elapsed,
        "frames": game.frame_count,
        "fps": game.frame_count / elapsed,
        "renderer": asdict(stats),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directional-lights", type=int, default=4)
    parser.add_argument("--point-lights", type=int, default=64)
    parser.add_argument("--spot-lights", type=int, default=32)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument(
        "--preset", choices=("low", "medium", "high", "ultra"), default="ultra"
    )
    arguments = parser.parse_args()
    if (
        arguments.directional_lights < 0
        or arguments.point_lights < 0
        or arguments.spot_lights < 0
    ):
        parser.error("light counts must be non-negative")
    if arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    print(json.dumps(run(
        directional_lights=arguments.directional_lights,
        point_lights=arguments.point_lights,
        spot_lights=arguments.spot_lights,
        seconds=arguments.seconds,
        preset=arguments.preset,
    ), indent=2))


if __name__ == "__main__":
    main()
