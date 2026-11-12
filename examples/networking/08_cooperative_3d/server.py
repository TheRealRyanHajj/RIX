"""Headless cooperative movement authority."""

# Usage: from the repository root, run:
#   python examples/networking/08_cooperative_3d/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import time

import rix
from rix import net

from schema import ASSIGNED, OBJECTIVE, PLAYER, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7784)
    args = parser.parse_args()
    replication_box: list[net.ServerReplication] = []
    players: dict[net.ConnectionId, net.NetworkObjectId] = {}

    def connected(server: net.Server, connection: net.ConnectionId) -> None:
        owner = replication_box[0]
        player = owner.spawn(PLAYER)
        player.entity.position = (len(players) * 1.5 - 1.5, 0.4, 3.0)
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        if owner.call_client(connection, player.id, ASSIGNED, player.id.value) is not net.SendStatus.QUEUED:
            server.disconnect(connection, "assignment backpressure")

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        identifier = players.pop(event.connection, None)
        owner = replication_box[0]
        if identifier is not None and any(item.id == identifier for item in owner.objects):
            owner.despawn(identifier)

    server = net.Server(
        port=args.port,
        bind_address="0.0.0.0",
        tick_rate=60,
        on_connect=connected,
        on_disconnect=disconnected,
    )
    scene = rix.Scene("cooperative authority")
    server.load_scene(scene)
    owner = net.ServerReplication(server, registry())
    replication_box.append(owner)
    objective = owner.spawn(OBJECTIVE)
    objective.entity.position = (0, 0.65, -4)
    server.start()
    print(f"cooperative server on UDP {args.port}; Ctrl+C stops it")
    try:
        while True:
            started = time.perf_counter()
            server.step()
            owner.flush_transforms(server.tick_count)
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        owner.close(destroy=True)
        server.stop("operator stopped")
        server.unload_scene(clear=True)
        scene.close()


if __name__ == "__main__":
    main()
