from __future__ import annotations

import time

import pytest

from easy3d import Entity, NetworkError, Scene, Server, network, replication


def _server_calls_registry(
    server_calls: list[tuple[str, network.ConnectionId, tuple[object, ...]]],
    client_calls: list[tuple[str, str]],
) -> replication.PrefabRegistry:
    registry = replication.PrefabRegistry(schema_version=10)
    registry.register(1, "actor", lambda scene: Entity("actor", scene=scene))

    def receive_server(
        entity: Entity, connection: network.ConnectionId, *values: object
    ) -> None:
        server_calls.append((entity.scene.name, connection, values))

    def receive_client(entity: Entity, message: object) -> None:
        client_calls.append((entity.scene.name, str(message)))

    registry.register_rpc(
        1,
        1,
        "submit",
        "client_to_server",
        (("bool", 1), ("int", 8), ("float", 8), ("string", 16), ("bytes", 4)),
        receive_server,
        reliable=True,
        rate_limit=2,
        require_owner=True,
    )
    registry.register_rpc(
        1,
        2,
        "notify",
        replication.RpcDirection.SERVER_TO_CLIENT,
        ((replication.NetworkValueType.STRING, 16),),
        receive_client,
        reliable=False,
        rate_limit=20,
    )
    return registry


def _server() -> Server:
    for port in range(32700, 32800):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind RPC test server")


def _pump(
    server: Server,
    replicas: tuple[replication.ClientReplication, ...],
    predicate,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not predicate():
        server.poll()
        for replica in replicas:
            replica.poll()
        time.sleep(0.001)
    assert predicate()


def test_rpc_schema_is_bounded_and_fingerprinted() -> None:
    server_calls: list[tuple[str, network.ConnectionId, tuple[object, ...]]] = []
    client_calls: list[tuple[str, str]] = []
    registry = _server_calls_registry(server_calls, client_calls)
    submit, notify = registry.rpcs(1)
    assert submit.delivery is network.Delivery.RELIABLE
    assert submit.require_owner and submit.rate_limit == 2
    assert notify.delivery is network.Delivery.UNRELIABLE

    changed = replication.PrefabRegistry(schema_version=10)
    changed.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    changed.register_rpc(
        1,
        1,
        "submit",
        "client_to_server",
        (("int", 8),),
        lambda *_args: None,
    )
    assert changed.fingerprint != registry.fingerprint
    with pytest.raises(ValueError, match="unique"):
        registry.register_rpc(
            1, 1, "duplicate", "client_to_server", (), lambda *_args: None
        )
    with pytest.raises(ValueError, match="at most 16"):
        registry.register_rpc(
            1,
            3,
            "too_many",
            "client_to_server",
            tuple(("int", 8) for _ in range(17)),
            lambda *_args: None,
        )
    with pytest.raises(ValueError, match="cannot require"):
        registry.register_rpc(
            1,
            3,
            "invalid_owner",
            "server_to_client",
            (),
            lambda *_args: None,
            require_owner=True,
        )


def test_loopback_rpc_dispatch_rate_limit_and_ownership_guard() -> None:
    server_calls: list[tuple[str, network.ConnectionId, tuple[object, ...]]] = []
    client_calls: list[tuple[str, str]] = []
    registry = _server_calls_registry(server_calls, client_calls)
    server = _server()
    server.load_scene(Scene("rpc authority"))
    owner = replication.ServerReplication(server, registry)
    spawned = owner.spawn(1)
    first_client = network.Client(timeout=1, peer_timeout=2)
    first = replication.ClientReplication(first_client, Scene("first rpc"), registry)
    second_client = network.Client(timeout=1, peer_timeout=2)
    second = replication.ClientReplication(second_client, Scene("second rpc"), registry)
    try:
        first_client.connect("127.0.0.1", server.port)
        second_client.connect("127.0.0.1", server.port)
        _pump(
            server,
            (first, second),
            lambda: first.is_synchronized and second.is_synchronized,
        )
        first_connection, second_connection = server.connections
        owner.set_owner(spawned.id, first_connection)
        assert owner.owner(spawned.id) == first_connection

        assert first.call_server(
            spawned.id, 1, True, 7, 1.25, "hello", b"abcd"
        ) is network.SendStatus.QUEUED
        _pump(server, (first, second), lambda: len(server_calls) == 1)
        assert server_calls[0] == (
            "rpc authority",
            first_connection,
            (True, 7, 1.25, "hello", b"abcd"),
        )

        assert owner.call_client(
            first_connection, spawned.id, 2, "accepted"
        ) is network.SendStatus.QUEUED
        _pump(server, (first, second), lambda: client_calls == [("first rpc", "accepted")])
        with pytest.raises(PermissionError, match="direction"):
            first.call_server(spawned.id, 2, "wrong")
        with pytest.raises(PermissionError, match="direction"):
            owner.call_client(first_connection, spawned.id, 1, True, 1, 1.0, "x", b"")

        assert first.call_server(
            spawned.id, 1, False, 8, 2.5, "two", b"b"
        ) is network.SendStatus.QUEUED
        assert first.call_server(
            spawned.id, 1, False, 9, 3.5, "three", b"c"
        ) is network.SendStatus.QUEUED
        _pump(server, (first, second), lambda: owner.rpc_stats.received == 3)
        assert len(server_calls) == 2
        assert owner.rpc_stats == replication.RpcStats(3, 2, 1)

        assert second.call_server(
            spawned.id, 1, True, 10, 4.5, "tamper", b"d"
        ) is network.SendStatus.QUEUED
        _pump(
            server,
            (first, second),
            lambda: second_client.state is network.ClientState.DISCONNECTED,
        )
        assert len(server_calls) == 2
        assert owner.owner(spawned.id) == first_connection

        duplicate = replication._rpc_frame(
            spawned.id,
            registry.rpc(1, 1),
            3,
            (False, 9, 3.5, "three", b"c"),
        )
        assert first_client.send(duplicate) is network.SendStatus.QUEUED
        _pump(
            server,
            (first,),
            lambda: first_client.state is network.ClientState.DISCONNECTED,
        )
        assert len(server_calls) == 2
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


def test_rpc_codec_rejects_argument_errors_and_root_exports() -> None:
    import easy3d

    registry = _server_calls_registry([], [])
    spec = registry.rpc(1, 1)
    with pytest.raises(TypeError, match="count"):
        replication._rpc_frame(replication.NetworkObjectId(1), spec, 1, ())
    with pytest.raises(ValueError, match="byte bound"):
        replication._rpc_frame(
            replication.NetworkObjectId(1),
            spec,
            1,
            (True, 1, 1.0, "this string is too long", b""),
        )
    assert easy3d.RpcDirection is replication.RpcDirection
    assert easy3d.RpcSpec is replication.RpcSpec
    assert easy3d.RpcStats is replication.RpcStats
