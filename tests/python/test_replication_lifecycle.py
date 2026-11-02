from __future__ import annotations

import time

import pytest

from easy3d import Entity, NetworkError, Scene, Server, network, replication


def _registry(name: str = "crate") -> replication.PrefabRegistry:
    registry = replication.PrefabRegistry(schema_version=7, capacity=4)
    registry.register(10, name, lambda scene: Entity(name, scene=scene))
    return registry


def _server(**arguments: object) -> Server:
    for port in range(32400, 32500):
        server = Server(
            port=port,
            bind_address="127.0.0.1",
            peer_timeout=2.0,
            **arguments,  # type: ignore[arg-type]
        )
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind a replication test port")


def _synchronize(
    server: Server,
    replica: replication.ClientReplication,
    *,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not replica.is_synchronized:
        server.poll()
        replica.poll()
        time.sleep(0.001)
    assert replica.is_synchronized


def _pump_object_count(
    server: Server,
    replica: replication.ClientReplication,
    count: int,
) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(replica.objects) != count:
        server.poll()
        replica.poll()
        time.sleep(0.001)
    assert len(replica.objects) == count


def test_prefab_registry_is_explicit_bounded_and_order_independent() -> None:
    first = replication.PrefabRegistry(schema_version=3, capacity=2)
    second = replication.PrefabRegistry(schema_version=3, capacity=2)
    factory = lambda scene: Entity("factory", scene=scene)
    first.register(2, "second", factory)
    first.register(1, "first", factory)
    second.register(1, "first", factory)
    second.register(2, "second", factory)
    assert first.fingerprint == second.fingerprint
    assert [item.id.value for item in first.registrations] == [1, 2]
    with pytest.raises(NetworkError, match="capacity"):
        first.register(3, "third", factory)
    with pytest.raises(ValueError, match="unique"):
        second.register(1, "duplicate", factory)
    second.freeze()
    with pytest.raises(RuntimeError, match="frozen"):
        second.register(3, "third", factory)
    with pytest.raises(ValueError):
        replication.NetworkObjectId(0)
    with pytest.raises(ValueError):
        replication.PrefabId(0)


def test_server_ids_never_reuse_and_existing_callbacks_are_preserved() -> None:
    connected: list[network.ConnectionId] = []
    server = _server(on_connect=lambda _server, value: connected.append(value))
    scene = Scene("authority")
    server.load_scene(scene)
    owner = replication.ServerReplication(server, _registry(), max_objects=2)
    try:
        first = owner.spawn(10)
        assert first.id.value == 1
        removed = owner.despawn(first.id)
        assert not removed.is_alive
        second = owner.spawn(10)
        assert second.id.value == 2
        assert second.entity.id != first.entity.id or not first.entity.is_alive
        with pytest.raises(RuntimeError, match="already"):
            replication.ServerReplication(server, _registry())
    finally:
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)
    assert connected == []


def test_live_spawn_despawn_and_late_join_use_stable_ids() -> None:
    callback_connections: list[network.ConnectionId] = []
    server = _server(
        on_connect=lambda _server, connection: callback_connections.append(connection)
    )
    authority_scene = Scene("authority")
    server.load_scene(authority_scene)
    registry = _registry()
    owner = replication.ServerReplication(server, registry, max_objects=8)
    first_client = network.Client(timeout=1.0, peer_timeout=2.0)
    first_scene = Scene("client one")
    first_replica = replication.ClientReplication(
        first_client, first_scene, registry, max_objects=8
    )
    second_client: network.Client | None = None
    second_replica: replication.ClientReplication | None = None
    try:
        first = owner.spawn(10)
        second = owner.spawn(10)
        first_client.connect("127.0.0.1", server.port)
        _synchronize(server, first_replica)
        assert [item.id for item in first_replica.objects] == [first.id, second.id]
        assert len(callback_connections) == 1

        third = owner.spawn(10)
        _pump_object_count(server, first_replica, 3)
        first_client_entity = first_replica.objects[0].entity
        owner.despawn(first.id)
        _pump_object_count(server, first_replica, 2)
        assert not first_client_entity.is_alive
        assert [item.id for item in first_replica.objects] == [second.id, third.id]

        second_client = network.Client(timeout=1.0, peer_timeout=2.0)
        second_scene = Scene("late join")
        second_replica = replication.ClientReplication(
            second_client, second_scene, registry, max_objects=8
        )
        second_client.connect("127.0.0.1", server.port)
        _synchronize(server, second_replica)
        assert [item.id for item in second_replica.objects] == [second.id, third.id]
        assert len(callback_connections) == 2
    finally:
        first_replica.clear()
        if first_client.connection is not None:
            first_client.disconnect("test complete")
            first_client.poll()
        if second_replica is not None:
            second_replica.clear()
        if second_client is not None and second_client.connection is not None:
            second_client.disconnect("test complete")
            second_client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_schema_mismatch_and_duplicate_spawn_are_rejected() -> None:
    server = _server()
    server.load_scene(Scene("authority mismatch"))
    owner = replication.ServerReplication(server, _registry("server crate"))
    owner.spawn(10)
    client = network.Client(timeout=1.0, peer_timeout=2.0)
    replica = replication.ClientReplication(
        client, Scene("mismatch client"), _registry("client crate")
    )
    try:
        client.connect("127.0.0.1", server.port)
        deadline = time.monotonic() + 2.0
        observed = False
        while time.monotonic() < deadline and not observed:
            server.poll()
            try:
                replica.poll()
            except NetworkError as error:
                assert "fingerprint mismatch" in str(error)
                observed = True
            time.sleep(0.001)
        assert observed

        local = network.Client(timeout=1.0)
        local_replica = replication.ClientReplication(
            local, Scene("codec"), _registry(), max_objects=2
        )
        registry = local_replica._registry
        begin = replication._frame(
            replication._BEGIN,
            replication._BEGIN_PAYLOAD.pack(1, 1, registry.schema_version, registry.fingerprint),
        )
        spawn = replication._frame(
            replication._SPAWN, replication._SPAWN_PAYLOAD.pack(1, 10)
        )
        local_replica._apply(begin)
        local_replica._apply(spawn)
        with pytest.raises(ValueError, match="duplicate"):
            local_replica._apply(spawn)
        local_replica.clear()
    finally:
        replica.clear()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_root_exports() -> None:
    import easy3d

    assert easy3d.NetworkObjectId is replication.NetworkObjectId
    assert easy3d.ServerReplication is replication.ServerReplication
