"""Pygame-only shared cursors using authoritative named messages."""

from __future__ import annotations

import argparse
import math

import pygame

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true")
    parser.add_argument("--address", default="127.0.0.1:7778")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((900, 600), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    session = net.Session()
    session.register_message("cursor", x=float, y=float)
    session.register_message("snapshot", players=dict)
    authoritative: dict[int, tuple[float, float]] = {}
    visible: dict[int, tuple[float, float]] = {}

    @session.on("cursor")
    def cursor(sender: net.Player, *, x: float, y: float) -> None:
        if not args.host or not math.isfinite(x) or not math.isfinite(y):
            return
        authoritative[sender.id] = (
            min(1.0, max(0.0, x)),
            min(1.0, max(0.0, y)),
        )
        session.broadcast(
            "snapshot",
            players={str(key): list(value) for key, value in authoritative.items()},
            unreliable=True,
        )

    @session.on("disconnect")
    def disconnected(player: net.Player, _reason: str) -> None:
        if args.host:
            authoritative.pop(player.id, None)

    @session.on("snapshot")
    def snapshot(_sender: net.Player, *, players: dict[str, object]) -> None:
        parsed: dict[int, tuple[float, float]] = {}
        for key, value in players.items():
            if isinstance(value, list) and len(value) == 2:
                parsed[int(key)] = (float(value[0]), float(value[1]))
        visible.clear()
        visible.update(parsed)

    try:
        if args.host:
            session.host(port=7778, max_players=8)
        else:
            session.join(args.address)
        while session.is_open:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
            x, y = pygame.mouse.get_pos()
            width, height = screen.get_size()
            session.send(
                "cursor",
                x=x / max(1, width),
                y=y / max(1, height),
                unreliable=True,
            )
            session.update(dt)
            screen.fill("#0f172a")
            for player, position in visible.items():
                point = (int(position[0] * width), int(position[1] * height))
                pygame.draw.circle(screen, "#38bdf8" if player % 2 else "#f59e0b", point, 12)
            pygame.display.flip()
    finally:
        session.close()
        pygame.quit()


if __name__ == "__main__":
    main()
