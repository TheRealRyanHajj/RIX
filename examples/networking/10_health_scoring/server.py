"""Headless replicated health/score authority."""

from __future__ import annotations

import argparse

import rix
from rix import net

from schema import ASSIGNED, PLAYER, registry, set_authority


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7786)
    args = parser.parse_args()
    owner_box: list[net.ServerReplication] = []
    players: dict[net.ConnectionId, net.NetworkObjectId] = {}

    def connected(server: net.Server, connection: net.ConnectionId) -> None:
        owner = owner_box[0]
        player = owner.spawn(PLAYER)
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        if owner.call_client(connection, player.id, ASSIGNED, player.id.value) is not net.SendStatus.QUEUED:
            server.disconnect(connection, "assignment backpressure")

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        identifier = players.pop(event.connection, None)
        owner = owner_box[0]
        if identifier is not None and any(item.id == identifier for item in owner.objects):
            owner.despawn(identifier)

    server = net.Server(
        port=args.port,
        bind_address="0.0.0.0",
        on_connect=connected,
        on_disconnect=disconnected,
    )
    scene = rix.Scene("score authority")
    server.load_scene(scene)
    owner = net.ServerReplication(server, registry())
    owner_box.append(owner)
    set_authority(owner)
    print(f"health/score authority on UDP {args.port}; Ctrl+C stops it")
    try:
        server.run()
    except KeyboardInterrupt:
        server.stop("operator interrupted")
    finally:
        owner.close(destroy=True)
        server.unload_scene(clear=True)
        scene.close()


if __name__ == "__main__":
    main()
