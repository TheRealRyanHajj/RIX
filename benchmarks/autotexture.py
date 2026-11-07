"""Measure AutoTexture generation, sharing, construction, and reload costs."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time

import rix as e3


def _measure(objects: int, cache_loads: int) -> dict[str, float | int]:
    with tempfile.TemporaryDirectory(prefix="rix_autotexture_") as directory:
        root = Path(directory)
        texture = root / "shared.png"

        scene = e3.Scene("AutoTexture benchmark seed")
        started = time.perf_counter_ns()
        e3.Cube(texture=texture, scene=scene)
        generation_ns = time.perf_counter_ns() - started
        scene.close()

        cache = e3.TextureCache()
        started = time.perf_counter_ns()
        for _ in range(cache_loads):
            cache.load(texture)
        cache_ns = time.perf_counter_ns() - started
        unique_cache_entries = len(cache)

        scene = e3.Scene("AutoTexture shared construction")
        started = time.perf_counter_ns()
        for index in range(objects):
            e3.Cube(
                x=float(index % 100),
                y=float(index // 100),
                texture=texture,
                scene=scene,
            )
        construction_ns = time.perf_counter_ns() - started
        scene.close()

        replacement = root / "replacement.png"
        replacement_scene = e3.Scene("AutoTexture replacement seed")
        e3.Sphere(texture=replacement, scene=replacement_scene)
        replacement_scene.close()
        stamp = time.time_ns() + 2_000_000_000
        texture.write_bytes(replacement.read_bytes())
        os.utime(texture, ns=(stamp, stamp))
        started = time.perf_counter_ns()
        updated = cache.poll_changes()
        reload_ns = time.perf_counter_ns() - started

        hits = cache_loads - unique_cache_entries
        return {
            "objects": objects,
            "generation_ns": generation_ns,
            "construction_ns": construction_ns,
            "ns_per_object": construction_ns / objects,
            "cache_loads": cache_loads,
            "cache_entries": unique_cache_entries,
            "cache_hit_rate": hits / cache_loads,
            "ns_per_cache_load": cache_ns / cache_loads,
            "reload_updates": updated,
            "reload_ns": reload_ns,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects", type=int, default=2_000)
    parser.add_argument("--cache-loads", type=int, default=10_000)
    arguments = parser.parse_args()
    if arguments.objects <= 0 or arguments.cache_loads <= 0:
        parser.error("counts must be positive")
    print(json.dumps(_measure(arguments.objects, arguments.cache_loads), indent=2))


if __name__ == "__main__":
    main()
