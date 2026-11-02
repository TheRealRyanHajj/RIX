"""Minimal headless authoritative Easy3D server."""

from __future__ import annotations

import argparse
import threading

from easy3d import Entity, Scene, Server
from easy3d.network import ConnectionId, NetworkEvent


class WorldLogic(Entity):
    """Example Python-only authoritative simulation behavior."""

    def __init__(self, *, scene: Scene) -> None:
        self.ticks = 0
        super().__init__("WorldLogic", scene=scene)

    def fixed_update(self, _dt: float) -> None:
        self.ticks += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0", help="numeric bind address")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--tick-rate", type=float, default=60.0)
    parser.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="stop automatically after this many seconds; zero waits for Ctrl+C",
    )
    arguments = parser.parse_args()

    def connected(_server: Server, connection: ConnectionId) -> None:
        print(f"client connected: {connection.value}")

    def disconnected(_server: Server, event: NetworkEvent) -> None:
        print(
            f"client disconnected: {event.connection.value} "
            f"code={event.disconnect_code} reason={event.reason!r}"
        )

    server = Server(
        bind_address=arguments.bind,
        port=arguments.port,
        tick_rate=arguments.tick_rate,
        on_connect=connected,
        on_disconnect=disconnected,
    )
    scene = Scene("DedicatedWorld")
    logic = WorldLogic(scene=scene)
    server.load_scene(scene)

    timer = None
    if arguments.seconds > 0:
        timer = threading.Timer(
            arguments.seconds,
            lambda: server.stop("example duration complete"),
        )
        timer.daemon = True
        timer.start()

    print(
        f"Easy3D dedicated server listening on "
        f"{arguments.bind}:{arguments.port} at {arguments.tick_rate:g} Hz"
    )
    try:
        server.run()
    except KeyboardInterrupt:
        server.stop("operator interrupted")
    finally:
        if timer is not None:
            timer.cancel()
        print(f"server stopped after {logic.ticks} authoritative ticks")


if __name__ == "__main__":
    main()
