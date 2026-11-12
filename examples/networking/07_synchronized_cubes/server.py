"""Headless authority for the synchronized-cubes client."""

# Usage: from the repository root, run:
#   python examples/networking/07_synchronized_cubes/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import math
import time

import rix
from rix import net

from schema import CUBE, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7783)
    args = parser.parse_args()
    server = net.Server(port=args.port, bind_address="0.0.0.0", tick_rate=60)
    scene = rix.Scene("cube authority")
    server.load_scene(scene)
    replication = net.ServerReplication(server, registry())
    cubes = [replication.spawn(CUBE) for _ in range(3)]
    server.start()
    print(f"cube authority on UDP {args.port}; Ctrl+C stops it")
    try:
        while True:
            started = time.perf_counter()
            server.step()
            tick = server.tick_count
            seconds = tick / 60.0
            for index, cube in enumerate(cubes):
                angle = seconds * 0.8 + index * math.tau / len(cubes)
                cube.entity.position = (
                    math.cos(angle) * 2.5,
                    0.5 + index * 0.4,
                    math.sin(angle) * 2.5,
                )
                cube.entity.ry = math.degrees(angle)
            replication.flush_transforms(tick)
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        replication.close(destroy=True)
        server.stop("operator stopped")
        server.unload_scene(clear=True)
        scene.close()


if __name__ == "__main__":
    main()
