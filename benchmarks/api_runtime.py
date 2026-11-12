"""Compare scheduler traversal and native physics costs across RIX builds.

This intentionally uses the same internal frame seam as the test suite so it can run
without opening a window. It is a development benchmark, not a public performance
guarantee."""

# Usage: from the repository root, run:
#   python benchmarks/api_runtime.py
# This prints benchmark measurements.

from __future__ import annotations

import argparse
import json
import statistics
import time

import rix as e3


def _median_ns(samples: list[float]) -> float:
    return statistics.median(samples) * 1_000_000_000.0


def _advance_game(game: e3.Game, delta: float) -> None:
    """Run the scheduler seam shared by pre- and post-manual-loop builds."""

    game._callback_active = True
    try:
        game._scheduler.advance(game.scene, delta)
    finally:
        game._callback_active = False


def _callback_benchmark(callbacks: int, frames: int) -> dict[str, float | int]:
    game = e3.Game(auto_setup=True)
    calls = 0

    def callback(_delta: float) -> None:
        nonlocal calls
        calls += 1

    for _ in range(callbacks):
        game.subscribe_update(callback)

    game._scheduler.begin_run()
    frame_samples: list[float] = []
    for _ in range(frames):
        started = time.perf_counter()
        _advance_game(game, 1.0 / 60.0)
        frame_samples.append(time.perf_counter() - started)

    expected = callbacks * frames
    if calls != expected:
        raise RuntimeError(f"expected {expected} callback calls, observed {calls}")
    game.close()
    return {
        "callbacks": callbacks,
        "frames": frames,
        "calls": calls,
        "median_frame_ns": _median_ns(frame_samples),
        "median_ns_per_callback": _median_ns(frame_samples) / callbacks,
    }


def _scene_traversal_benchmark(entities: int, frames: int) -> dict[str, float | int]:
    game = e3.Game(auto_setup=True)
    calls = 0

    class BenchEntity(e3.Entity):
        def update(self, _delta: float) -> None:
            nonlocal calls
            calls += 1

    for index in range(entities):
        BenchEntity(f"bench-{index}")

    game._scheduler.begin_run()
    frame_samples: list[float] = []
    for _ in range(frames):
        started = time.perf_counter()
        _advance_game(game, 1.0 / 60.0)
        frame_samples.append(time.perf_counter() - started)

    expected = entities * frames
    if calls != expected:
        raise RuntimeError(f"expected {expected} entity updates, observed {calls}")
    game.close()
    return {
        "entities": entities,
        "frames": frames,
        "calls": calls,
        "median_frame_ns": _median_ns(frame_samples),
        "median_ns_per_entity": _median_ns(frame_samples) / entities,
    }


def _physics_benchmark(bodies: int, steps: int) -> dict[str, float | int]:
    game = e3.Game(auto_setup=True)
    e3.Plane(size=500, collider=True)
    for index in range(bodies):
        e3.Sphere(
            x=float(index % 20) * 2.5,
            y=5.0 + float(index // 20) * 2.5,
            z=float((index // 400) % 20) * 2.5,
            physics=True,
        )

    samples: list[float] = []
    for _ in range(steps):
        started = time.perf_counter()
        game.scene._native.step_physics(1.0 / 60.0)
        samples.append(time.perf_counter() - started)
    game.close()
    return {
        "bodies": bodies,
        "steps": steps,
        "median_step_ns": _median_ns(samples),
        "median_ns_per_body": _median_ns(samples) / bodies,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--callbacks", type=int, default=500)
    parser.add_argument("--entities", type=int, default=500)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--bodies", type=int, default=200)
    parser.add_argument("--steps", type=int, default=180)
    args = parser.parse_args()
    if min(args.callbacks, args.entities, args.frames, args.bodies, args.steps) <= 0:
        parser.error("all counts must be positive")

    print(
        json.dumps(
            {
                "callbacks": _callback_benchmark(args.callbacks, args.frames),
                "scene_traversal": _scene_traversal_benchmark(args.entities, args.frames),
                "physics": _physics_benchmark(args.bodies, args.steps),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
