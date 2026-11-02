"""Finite 2–8 client cooperative replication scenario over real loopback."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

from easy3d import Entity, NetworkError, Scene, Server, network, replication


PLAYER = 1
CRATE = 2
HEALTH = 1
MOVE = 1
HIT = 2
ASSIGNED = 3


@dataclass(frozen=True, slots=True)
class SandboxResult:
    clients: int
    players: int
    synchronized_positions: int
    crate_destroyed: bool
    rpc_executed: int


def _listen_server(on_connect, on_disconnect) -> Server:  # type: ignore[no-untyped-def]
    for port in range(32900, 33000):
        server = Server(
            port=port,
            bind_address="127.0.0.1",
            peer_timeout=2,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise RuntimeError("no loopback sandbox port is available")


def _pump(
    server: Server,
    mirrors: list[replication.ClientReplication],
    predicate,
    *,
    timeout: float = 3.0,
) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        server.poll()
        for mirror in mirrors:
            mirror.poll()
        time.sleep(0.001)
    if not predicate():
        raise RuntimeError("sandbox scenario timed out")


def run_sandbox(client_count: int = 2) -> SandboxResult:
    if isinstance(client_count, bool) or not isinstance(client_count, int):
        raise TypeError("client_count must be an integer")
    if not 2 <= client_count <= 8:
        raise ValueError("client_count must be in [2, 8]")

    assignments: dict[str, replication.NetworkObjectId] = {}
    players: dict[network.ConnectionId, replication.NetworkObjectId] = {}
    owner_box: list[replication.ServerReplication] = []
    crate_box: list[replication.NetworkObjectId] = []

    def assign(entity: Entity, object_value: object) -> None:
        assignments[entity.scene.name] = replication.NetworkObjectId(int(object_value))

    def move(
        entity: Entity,
        _sender: network.ConnectionId,
        x_value: object,
        z_value: object,
    ) -> None:
        x, z = float(x_value), float(z_value)
        if abs(x) <= 20 and abs(z) <= 20:
            entity.position = (x, 0, z)

    def hit(
        entity: Entity,
        _sender: network.ConnectionId,
        target_value: object,
    ) -> None:
        owner = owner_box[0]
        target_id = replication.NetworkObjectId(int(target_value))
        target = next((item for item in owner.objects if item.id == target_id), None)
        if target is None or target.prefab_id.value != CRATE:
            return
        delta = entity.position - target.entity.position
        if delta.length_squared > 25:
            return
        health = owner.variable(target_id, HEALTH)
        health.value = max(0, int(health.value) - 50)
        owner.flush()
        if health.value == 0:
            owner.despawn(target_id)

    registry = replication.PrefabRegistry(schema_version=12)
    registry.register(PLAYER, "player", lambda scene: Entity("player", scene=scene))
    registry.register_variable(PLAYER, HEALTH, "health", "int", 100, max_bytes=8)
    registry.register_transform(PLAYER)
    registry.register_rpc(
        PLAYER,
        MOVE,
        "request_move",
        "client_to_server",
        (("float", 8), ("float", 8)),
        move,
        reliable=False,
        rate_limit=30,
        require_owner=True,
    )
    registry.register_rpc(
        PLAYER,
        HIT,
        "request_hit",
        "client_to_server",
        (("int", 8),),
        hit,
        reliable=True,
        rate_limit=10,
        require_owner=True,
    )
    registry.register_rpc(
        PLAYER,
        ASSIGNED,
        "assigned_player",
        "server_to_client",
        (("int", 8),),
        assign,
        reliable=True,
        rate_limit=10,
    )
    registry.register(CRATE, "crate", lambda scene: Entity("crate", scene=scene))
    registry.register_variable(CRATE, HEALTH, "health", "int", 100, max_bytes=8)

    def connected(server: Server, connection: network.ConnectionId) -> None:
        owner = owner_box[0]
        player = owner.spawn(PLAYER)
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        status = owner.call_client(connection, player.id, ASSIGNED, player.id.value)
        if status is not network.SendStatus.QUEUED:
            server.disconnect(connection, "player assignment backpressure")

    def disconnected(_server: Server, event: network.NetworkEvent) -> None:
        object_id = players.pop(event.connection, None)
        if object_id is not None and any(item.id == object_id for item in owner_box[0].objects):
            owner_box[0].despawn(object_id)

    server = _listen_server(connected, disconnected)
    server.load_scene(Scene("sandbox authority"))
    owner = replication.ServerReplication(server, registry, max_objects=32)
    owner_box.append(owner)
    crate = owner.spawn(CRATE)
    crate_box.append(crate.id)
    clients: list[network.Client] = []
    mirrors: list[replication.ClientReplication] = []
    try:
        for index in range(client_count):
            client = network.Client(timeout=1, peer_timeout=2)
            mirror = replication.ClientReplication(
                client, Scene(f"sandbox client {index}"), registry, max_objects=32
            )
            clients.append(client)
            mirrors.append(mirror)
            client.connect("127.0.0.1", server.port)
        _pump(
            server,
            mirrors,
            lambda: all(mirror.is_synchronized for mirror in mirrors)
            and len(assignments) == client_count
            and all(len(mirror.objects) == client_count + 1 for mirror in mirrors),
        )

        for index, mirror in enumerate(mirrors):
            owned = assignments[mirror.objects[0].entity.scene.name]
            x = (index - (client_count - 1) / 2.0) * 0.5
            if mirror.call_server(owned, MOVE, x, 1.0) is not network.SendStatus.QUEUED:
                raise RuntimeError("move request was not queued")
        _pump(server, mirrors, lambda: owner.rpc_stats.executed >= client_count)
        transform_stats = owner.flush_transforms(1)
        if transform_stats.queued != client_count * client_count:
            raise RuntimeError("not every player transform was queued to every client")
        _pump(
            server,
            mirrors,
            lambda: all(
                sum(bool(mirror.transform_snapshots(item.id)) for item in mirror.objects if item.prefab_id.value == PLAYER)
                == client_count
                for mirror in mirrors
            ),
        )
        synchronized_positions = 0
        for mirror in mirrors:
            synchronized_positions += mirror.interpolate_transforms(1)

        for mirror in mirrors[:2]:
            owned = assignments[mirror.objects[0].entity.scene.name]
            if mirror.call_server(owned, HIT, crate.id.value) is not network.SendStatus.QUEUED:
                raise RuntimeError("hit request was not queued")
        _pump(
            server,
            mirrors,
            lambda: all(
                all(item.prefab_id.value != CRATE for item in mirror.objects)
                for mirror in mirrors
            ),
        )
        return SandboxResult(
            client_count,
            len(players),
            synchronized_positions,
            not any(item.id == crate.id for item in owner.objects),
            owner.rpc_stats.executed,
        )
    finally:
        for mirror in mirrors:
            mirror.clear()
        for client in clients:
            if client.connection is not None:
                client.disconnect("sandbox complete")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=2, choices=range(2, 9))
    args = parser.parse_args()
    result = run_sandbox(args.clients)
    print(
        f"sandbox complete: clients={result.clients} players={result.players} "
        f"interpolated={result.synchronized_positions} "
        f"crate_destroyed={result.crate_destroyed} rpc_executed={result.rpc_executed}"
    )


if __name__ == "__main__":
    main()
