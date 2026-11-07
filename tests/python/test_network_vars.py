from __future__ import annotations

import time

import pytest

from rix import Entity, Scene
from rix import net as network
from rix.net import NetworkError, Server, replication


def _registry() -> replication.PrefabRegistry:
    result = replication.PrefabRegistry(schema_version=8)
    result.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    result.register_variable(1, 1, "alive", "bool", True, max_bytes=1)
    result.register_variable(1, 2, "score", "int", 0, max_bytes=8)
    result.register_variable(1, 3, "speed", "float", 1.5, max_bytes=8)
    result.register_variable(1, 4, "label", "string", "new", max_bytes=12)
    result.register_variable(1, 5, "token", "bytes", b"", max_bytes=4)
    return result


def _server() -> Server:
    for port in range(32500, 32600):
        value = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            value.start()
            return value
        except NetworkError:
            continue
    raise AssertionError("could not bind NetworkVar test server")


def _sync(server: Server, mirror: replication.ClientReplication) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not mirror.is_synchronized:
        server.poll()
        mirror.poll()
        time.sleep(0.001)
    assert mirror.is_synchronized


def test_variable_schema_validation_and_fingerprint() -> None:
    registry = _registry()
    assert [item.id for item in registry.variables(1)] == [1, 2, 3, 4, 5]
    changed = _registry()
    changed._fields[replication.PrefabId(1)][2] = replication.NetworkVarSpec(
        2, "score", replication.NetworkValueType.INT, 1, 8
    )
    assert changed.fingerprint != registry.fingerprint
    with pytest.raises(ValueError, match="unique"):
        registry.register_variable(1, 1, "again", "int", 0)
    with pytest.raises(ValueError, match="bound"):
        registry.register_variable(1, 6, "tiny", "string", "too long", max_bytes=2)
    with pytest.raises(ValueError, match="finite"):
        registry.register_variable(1, 6, "bad", "float", float("nan"))
    with pytest.raises(TypeError, match="requires int"):
        registry.register_variable(1, 6, "bad", "int", True)
    with pytest.raises(ValueError, match="bound"):
        registry.register_variable(1, 6, "bad", "int", 0, max_bytes=1)


def test_network_var_dirty_tracking_and_client_authority_guard() -> None:
    spec = replication.NetworkVarSpec(
        1, "score", replication.NetworkValueType.INT, 0, 8
    )
    authority = replication.NetworkVar(spec, authority=True)
    authority.value = 0
    assert not authority.dirty and authority.version == 0
    authority.value = 9
    assert authority.dirty and authority.version == 1 and authority.value == 9
    with pytest.raises(ValueError, match="int64"):
        authority.value = 2**63
    mirror = replication.NetworkVar(spec, authority=False)
    with pytest.raises(PermissionError, match="read-only"):
        mirror.value = 1


def test_live_values_flush_and_late_join_current_state() -> None:
    server = _server()
    server.load_scene(Scene("var authority"))
    registry = _registry()
    owner = replication.ServerReplication(server, registry)
    spawned = owner.spawn(1)
    client = network.Client(timeout=1, peer_timeout=2)
    mirror = replication.ClientReplication(client, Scene("var client"), registry)
    late_client: network.Client | None = None
    late: replication.ClientReplication | None = None
    try:
        client.connect("127.0.0.1", server.port)
        _sync(server, mirror)
        assert mirror.variable(spawned.id, 2).value == 0
        owner.variable(spawned.id, 1).value = False
        owner.variable(spawned.id, 2).value = 42
        owner.variable(spawned.id, 3).value = 3.25
        owner.variable(spawned.id, 4).value = "ready"
        owner.variable(spawned.id, 5).value = b"abcd"
        assert owner.flush() == 5
        assert owner.flush() == 0
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and mirror.variable(spawned.id, 2).value != 42:
            server.poll()
            mirror.poll()
            time.sleep(0.001)
        assert [mirror.variable(spawned.id, field).value for field in range(1, 6)] == [
            False,
            42,
            3.25,
            "ready",
            b"abcd",
        ]

        late_client = network.Client(timeout=1, peer_timeout=2)
        late = replication.ClientReplication(late_client, Scene("late vars"), registry)
        late_client.connect("127.0.0.1", server.port)
        _sync(server, late)
        assert late.variable(spawned.id, 2).value == 42
        assert late.variable(spawned.id, 2).version == 1

        stale = replication._value_frame(spawned.id, owner.variable(spawned.id, 2))
        # Exact same-version state is idempotent across a resync/live boundary.
        mirror._apply(stale)
        older = replication.NetworkVar(owner.variable(spawned.id, 2).spec, authority=True)
        with pytest.raises(ValueError, match="stale"):
            mirror._apply(replication._value_frame(spawned.id, older))
    finally:
        mirror.clear()
        if late is not None:
            late.clear()
        if client.connection is not None:
            client.disconnect("done")
            client.poll()
        if late_client is not None and late_client.connection is not None:
            late_client.disconnect("done")
            late_client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)
