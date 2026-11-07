"""Pygame scoreboard client; Space requests damage against another player."""

from __future__ import annotations

import argparse

import pygame
import rix
from rix import net

from schema import DAMAGE, HEALTH, SCORE, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7786)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((720, 480), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 38)
    scene = rix.Scene("score client")
    client = net.Client()
    mirror = net.ClientReplication(client, scene, registry())
    client.connect(args.address, args.port)
    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    local = next(
                        (
                            item
                            for item in mirror.objects
                            if getattr(item.entity, "network_local_id", None) == item.id.value
                        ),
                        None,
                    )
                    target = next(
                        (item for item in mirror.objects if local is not None and item.id != local.id),
                        None,
                    )
                    if local is not None and target is not None:
                        mirror.call_server(local.id, DAMAGE, target.id.value)
            mirror.poll()
            screen.fill("#111827")
            for row, item in enumerate(mirror.objects):
                health = int(mirror.variable(item.id, HEALTH).value)
                score = int(mirror.variable(item.id, SCORE).value)
                local = getattr(item.entity, "network_local_id", None) == item.id.value
                label = font.render(
                    f"{'You' if local else 'Player'} {item.id.value}: health {health}, score {score}",
                    True,
                    "#f59e0b" if local else "white",
                )
                screen.blit(label, (30, 40 + row * 52))
            pygame.display.flip()
            clock.tick(60)
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("client closed")
            client.poll()
        scene.close()
        pygame.quit()


if __name__ == "__main__":
    main()
