from __future__ import annotations

import time

import pytest

from rix import Entity, Scene
from rix.net import (
    Client,
    ClientReplication,
    ClientState,
    ConnectionId,
    NetworkError,
    NetworkEvent,
    NetworkObjectId,
    PrefabRegistry,
    SendStatus,
    Server,
    ServerReplication,
)
from rix.net import replication


def _registry() -> PrefabRegistry:
    registry = PrefabRegistry(schema_version=13)
    registry.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    registry.register_variable(1, 1, "score", "int", 0, max_bytes=8)
    registry.register_transform(1)
    return registry


def _server() -> Server:
    for port in range(33000, 33100):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind resync test server")


def _pump(server: Server, mirrors: tuple[ClientReplication, ...], predicate) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not predicate():
        server.poll()
        for mirror in mirrors:
            mirror.poll()
        time.sleep(0.001)
    assert predicate()


def test_resync_rebuilds_state_and_preserves_healthy_peer() -> None:
    server = _server()
    server.load_scene(Scene("resync authority"))
    registry = _registry()
    owner = ServerReplication(server, registry)
    spawned = owner.spawn(1)
    first_client = Client(timeout=1, peer_timeout=2)
    second_client = Client(timeout=1, peer_timeout=2)
    first = ClientReplication(first_client, Scene("resync first"), registry)
    second = ClientReplication(second_client, Scene("resync second"), registry)
    try:
        first_client.connect("127.0.0.1", server.port)
        second_client.connect("127.0.0.1", server.port)
        _pump(server, (first, second), lambda: first.is_synchronized and second.is_synchronized)
        old_entity = first.objects[0].entity
        first.variable(spawned.id, 1)._value = -999
        first._transform_history.clear()

        owner.variable(spawned.id, 1).value = 99
        spawned.entity.position = (5, 2, -1)
        assert first.request_resync() is SendStatus.QUEUED
        _pump(
            server,
            (first, second),
            lambda: first.variable(spawned.id, 1).value == 99
            and bool(first.transform_snapshots(spawned.id))
            and first.objects[0].entity.id != old_entity.id,
        )
        assert not old_entity.is_alive
        first.interpolate_transforms(0)
        assert tuple(first.objects[0].entity.position) == pytest.approx((5, 2, -1))
        assert second.is_synchronized and second.objects[0].entity.is_alive

        assert owner.flush() == 1
        _pump(server, (first, second), lambda: second.variable(spawned.id, 1).value == 99)
        assert first.variable(spawned.id, 1).value == 99
        assert first_client.state is ClientState.CONNECTED

        duplicate = replication._resync_frame(1)
        assert first_client.send(duplicate) is SendStatus.QUEUED
        _pump(
            server,
            (first, second),
            lambda: first_client.state is ClientState.DISCONNECTED,
        )
        assert second_client.state is ClientState.CONNECTED
        assert second.variable(spawned.id, 1).value == 99
    finally:
        first.clear()
        second.clear()
        for client in (first_client, second_client):
            if client.connection is not None:
                client.disconnect("done")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_resync_requires_live_synchronized_client() -> None:
    mirror = ClientReplication(Client(timeout=1), Scene("inactive resync"), _registry())
    assert mirror.request_resync() is SendStatus.INVALID_CONNECTION


def test_repeated_join_leave_clears_ownership_and_never_reuses_ids() -> None:
    owner_box: list[ServerReplication] = []
    connection_objects: dict[ConnectionId, NetworkObjectId] = {}
    allocated: list[int] = []

    def connected(_server: Server, connection: ConnectionId) -> None:
        item = owner_box[0].spawn(1)
        owner_box[0].set_owner(item.id, connection)
        connection_objects[connection] = item.id
        allocated.append(item.id.value)

    def disconnected(_server: Server, event: NetworkEvent) -> None:
        identifier = connection_objects.pop(event.connection, None)
        if identifier is not None:
            owner_box[0].despawn(identifier)

    for port in range(33100, 33200):
        server = Server(
            port=port,
            bind_address="127.0.0.1",
            peer_timeout=2,
            on_connect=connected,
            on_disconnect=disconnected,
        )
        try:
            server.start()
            break
        except NetworkError:
            continue
    else:
        raise AssertionError("could not bind churn test server")
    server.load_scene(Scene("churn authority"))
    registry = _registry()
    owner = ServerReplication(server, registry)
    owner_box.append(owner)
    try:
        for index in range(12):
            client = Client(timeout=1, peer_timeout=2)
            mirror = ClientReplication(client, Scene(f"churn client {index}"), registry)
            client.connect("127.0.0.1", server.port)
            _pump(server, (mirror,), lambda: mirror.is_synchronized and len(owner.objects) == 1)
            connection = server.connections[0]
            assert owner.owner(owner.objects[0].id) == connection
            client.disconnect("cycle complete")
            _pump(
                server,
                (mirror,),
                lambda: client.state is ClientState.DISCONNECTED
                and not server.connections
                and not owner.objects,
            )
            mirror.clear()
        assert allocated == list(range(1, 13))
        assert not connection_objects
    finally:
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)
