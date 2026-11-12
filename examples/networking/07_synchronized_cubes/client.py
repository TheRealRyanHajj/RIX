"""RIX 3D client interpolating registered authoritative cube transforms."""

# Usage: from the repository root, run:
#   python examples/networking/07_synchronized_cubes/client.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse

import pygame
import rix
from rix import net

from schema import registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7783)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    world = rix.World(screen)
    client = net.Client()
    mirror = net.ClientReplication(client, world.scene, registry())
    interpolator = net.RemoteTransformInterpolator(mirror, delay_ticks=2)
    client.connect(args.address, args.port)
    authority_tick = 0
    try:
        while world.running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                world.handle_event(event)
            mirror.poll()
            for item in mirror.objects:
                samples = mirror.transform_snapshots(item.id)
                if samples:
                    authority_tick = max(authority_tick, samples[-1].tick)
            if mirror.is_synchronized:
                interpolator.update(authority_tick)
            world.update(dt)
            world.render()
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("client closed")
            client.poll()
        world.close()
        pygame.quit()


if __name__ == "__main__":
    main()
