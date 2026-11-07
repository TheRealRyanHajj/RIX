"""Headless authoritative FPS-rules server."""

from __future__ import annotations

import argparse
import time

import rix
from rix import net

from schema import ASSIGNED, MATCH, PLAYER, registry, set_authority


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7785)
    args = parser.parse_args()
    owner_box: list[net.ServerReplication] = []
    match_box: list[net.ServerMatchState] = []
    players: dict[net.ConnectionId, net.NetworkObjectId] = {}

    def connected(server: net.Server, connection: net.ConnectionId) -> None:
        owner = owner_box[0]
        player = owner.spawn(PLAYER)
        index = len(players)
        player.entity.position = ((index % 4) * 3 - 4.5, 0.8, (index // 4) * 3)
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        if owner.call_client(connection, player.id, ASSIGNED, player.id.value) is not net.SendStatus.QUEUED:
            server.disconnect(connection, "assignment backpressure")
            return
        match = match_box[0]
        if len(players) >= 2 and match.phase in (
            net.MatchPhase.WAITING,
            net.MatchPhase.MATCH_END,
        ):
            match.start_match(server.tick_count, countdown_ticks=60)

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        identifier = players.pop(event.connection, None)
        owner = owner_box[0]
        if identifier is not None and any(item.id == identifier for item in owner.objects):
            owner.despawn(identifier)

    server = net.Server(
        port=args.port,
        bind_address="0.0.0.0",
        tick_rate=60,
        on_connect=connected,
        on_disconnect=disconnected,
    )
    scene = rix.Scene("FPS authority")
    server.load_scene(scene)
    owner = net.ServerReplication(server, registry())
    owner_box.append(owner)
    match_object = owner.spawn(MATCH)
    match = net.ServerMatchState(owner, match_object.id, countdown_ticks=60)
    match_box.append(match)
    set_authority(owner, match)
    server.start()
    print(f"authoritative FPS server on UDP {args.port}; connect two clients")
    try:
        while True:
            started = time.perf_counter()
            server.step()
            match.advance(server.tick_count)
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
