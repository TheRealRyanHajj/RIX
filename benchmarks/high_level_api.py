"""Compare convenience construction costs with equivalent explicit APIs."""

from __future__ import annotations

import argparse
import time

from rix import (
    Collider,
    Cube,
    Rigidbody,
    Scene,
)


def construction(count: int) -> tuple[float, float]:
    high_scene = Scene("high-level construction")
    start = time.perf_counter()
    with high_scene:
        for index in range(count):
            Cube(x=index % 100, y=index // 100, physics=True, mass=2)
    high_seconds = time.perf_counter() - start
    high_scene.close()

    explicit_scene = Scene("explicit construction")
    start = time.perf_counter()
    with explicit_scene:
        for index in range(count):
            cube = Cube(position=(index % 100, index // 100, 0))
            cube.add_component(Collider, shape="box", half_extents=(0.5, 0.5, 0.5))
            cube.add_component(Rigidbody, mass=2)
    explicit_seconds = time.perf_counter() - start
    explicit_scene.close()
    return high_seconds, explicit_seconds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objects", type=int, default=2_000)
    args = parser.parse_args()
    high, explicit = construction(args.objects)
    print(
        f"construction objects={args.objects} high={high:.6f}s "
        f"explicit={explicit:.6f}s ratio={high / explicit:.3f}"
    )


if __name__ == "__main__":
    main()
