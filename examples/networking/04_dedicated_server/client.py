"""Independent Pygame client for the dedicated safe-message server."""

# Usage: from the repository root, run:
#   python examples/networking/04_dedicated_server/client.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse

import pygame

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7780)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((640, 360), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 38)
    client = net.Client()
    client.connect(args.address, args.port)
    sequence = 0
    last_reply = -1

    try:
        running = True
        while running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    sequence += 1
                    client.send(net.encode_message("ping", {"sequence": sequence}))
            for event in client.poll():
                if event.type is net.EventType.MESSAGE:
                    message = net.decode_message(event.payload)
                    if message.name == "pong":
                        value = message.fields.get("sequence")
                        if isinstance(value, int) and not isinstance(value, bool):
                            last_reply = value
                elif event.type is net.EventType.DISCONNECTED:
                    running = False
            screen.fill("#111827")
            label = font.render(
                f"Space sends ping — last pong {last_reply}", True, "white"
            )
            screen.blit(label, (24, 150))
            pygame.display.flip()
    finally:
        if client.connection is not None:
            client.disconnect("client closed")
            client.poll()
        pygame.quit()


if __name__ == "__main__":
    main()
