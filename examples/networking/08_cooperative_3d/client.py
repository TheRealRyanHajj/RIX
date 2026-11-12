"""Independent Pygame+RIX cooperative movement client."""

# Usage: from the repository root, run:
#   python examples/networking/08_cooperative_3d/client.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse

import pygame
import rix
from rix import net

from schema import MOVE, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7784)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    world = rix.World(screen)
    rix.Plane(world, y=0, size=30, color="#334155")
    client = net.Client()
    mirror = net.ClientReplication(client, world.scene, registry())
    interpolation = net.RemoteTransformInterpolator(mirror, delay_ticks=2)
    client.connect(args.address, args.port)
    authority_tick = 0
    try:
        while world.running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                world.handle_event(event)
            mirror.poll()
            local = next(
                (
                    item
                    for item in mirror.objects
                    if getattr(item.entity, "network_local_id", None) == item.id.value
                ),
                None,
            )
            keys = pygame.key.get_pressed()
            x = float(keys[pygame.K_d] - keys[pygame.K_a])
            z = float(keys[pygame.K_s] - keys[pygame.K_w])
            if local is not None and (x or z):
                mirror.call_server(local.id, MOVE, x, z)
            for item in mirror.objects:
                samples = mirror.transform_snapshots(item.id)
                if samples:
                    authority_tick = max(authority_tick, samples[-1].tick)
            if mirror.is_synchronized:
                interpolation.update(authority_tick)
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
