"""Illustrates state-management pattern: 09 Headless Match.

Run from the repository root with `python examples/states/09_headless_match.py`. See
`examples/states/README.md` for the state-example index."""

import time

from rix import StateMachine, net

match = StateMachine("lobby")
players = 0


@match.state("lobby")
def lobby(_dt: float) -> None:
    print("waiting for players")


@match.state("playing")
def playing(_dt: float) -> None:
    print("authoritative match tick")


match.when("lobby", "playing", condition=lambda: players >= 2)


def connected(_server: net.Server, _connection: net.ConnectionId) -> None:
    global players
    players += 1


def disconnected(_server: net.Server, _event: net.NetworkEvent) -> None:
    global players
    players = max(0, players - 1)


server = net.Server(
    port=7777,
    tick_rate=60,
    on_connect=connected,
    on_disconnect=disconnected,
)
server.start()
print("headless match server on UDP 7777; Ctrl+C stops it")
try:
    while True:
        server.poll()
        match.update(1 / 60)
        time.sleep(1 / 60)
except KeyboardInterrupt:
    pass
finally:
    server.stop("example stopped")
