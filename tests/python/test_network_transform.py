from __future__ import annotations

import math
import time

import pytest

from easy3d import Entity, NetworkError, Quat, Scene, Server, network, replication


def _registry() -> replication.PrefabRegistry:
    registry = replication.PrefabRegistry(schema_version=9)
    registry.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    declaration = registry.register_transform(1)
    assert declaration == replication.NetworkTransform(replication.PrefabId(1))
    return registry


def _server() -> Server:
    for port in range(32600, 32700):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind transform replication test server")


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


def test_transform_schema_codec_interpolation_and_history_bounds() -> None:
    registry = _registry()
    without_transform = replication.PrefabRegistry(schema_version=9)
    without_transform.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    assert registry.fingerprint != without_transform.fingerprint
    with pytest.raises(ValueError, match="already"):
        registry.register_transform(1)

    authority_scene = Scene("codec authority")
    authority = Entity("authority actor", scene=authority_scene)
    source = replication.ReplicatedObject(
        replication.NetworkObjectId(1), replication.PrefabId(1), authority
    )
    client_scene = Scene("codec client")
    mirror = replication.ClientReplication(
        network.Client(timeout=1), client_scene, registry, max_transform_samples=2
    )
    begin = replication._frame(
        replication._BEGIN,
        replication._BEGIN_PAYLOAD.pack(
            1, 1, registry.schema_version, registry.fingerprint
        ),
    )
    spawn = replication._frame(
        replication._SPAWN, replication._SPAWN_PAYLOAD.pack(1, 1)
    )
    end = replication._frame(replication._END, replication._END_PAYLOAD.pack(1))

    authority.position = (0, 0, 0)
    authority.quaternion = Quat.from_euler((0, 0, 0))
    authority.scale = (1, 1, 1)
    first = replication._transform_frame(source, 1, 10)
    mirror._apply(begin)
    mirror._apply(spawn)
    mirror._apply(first)
    mirror._apply(end)

    authority.position = (10, 4, -2)
    authority.quaternion = Quat.from_euler((0, 120, 0))
    authority.scale = (3, 5, 7)
    second = replication._transform_frame(source, 2, 20)
    mirror._apply(second)
    assert mirror.interpolate_transforms(15) == 1
    replica = mirror.objects[0].entity
    assert tuple(replica.position) == pytest.approx((5, 2, -1))
    assert tuple(replica.scale) == pytest.approx((2, 3, 4))
    assert math.isclose(replica.quaternion.length, 1.0, abs_tol=1.0e-6)
    assert replica.quaternion.almost_equal(Quat.from_euler((0, 60, 0)), 1.0e-5)

    mirror._apply(first)
    assert mirror.transform_stats.stale_dropped == 1
    authority.position = (20, 8, -4)
    mirror._apply(replication._transform_frame(source, 3, 30))
    assert [item.tick for item in mirror.transform_snapshots(1)] == [20, 30]
    assert mirror.transform_stats.history_evictions == 1
    mirror.interpolate_transforms(0)
    assert tuple(replica.position) == pytest.approx((10, 4, -2))
    mirror.interpolate_transforms(100)
    assert tuple(replica.position) == pytest.approx((20, 8, -4))
    authority.scale = (-3, 5, 7)
    mirror._apply(replication._transform_frame(source, 4, 40))
    mirror.interpolate_transforms(35)
    assert replica.scale.x == pytest.approx(-3)
    mirror.clear()
    authority_scene.clear()


def test_loopback_relevance_and_late_join_transform_baseline() -> None:
    server = _server()
    server.load_scene(Scene("transform authority"))
    registry = _registry()
    relevant: set[network.ConnectionId] = set()
    owner = replication.ServerReplication(
        server,
        registry,
        relevance_filter=lambda connection, _item: connection in relevant,
    )
    spawned = owner.spawn(1)
    spawned.entity.position = (1, 2, 3)
    first_client = network.Client(timeout=1, peer_timeout=2)
    second_client = network.Client(timeout=1, peer_timeout=2)
    first = replication.ClientReplication(first_client, Scene("first"), registry)
    second = replication.ClientReplication(second_client, Scene("second"), registry)
    late_client: network.Client | None = None
    late: replication.ClientReplication | None = None
    try:
        first_client.connect("127.0.0.1", server.port)
        second_client.connect("127.0.0.1", server.port)
        _pump(
            server,
            (first, second),
            lambda: first.is_synchronized and second.is_synchronized,
        )
        connections = server.connections
        assert len(connections) == 2
        relevant.add(connections[0])
        stats = owner.flush_transforms(10)
        assert (stats.queued, stats.filtered, stats.backpressured) == (1, 1, 0)
        _pump(
            server,
            (first, second),
            lambda: sum(
                bool(replica.transform_snapshots(spawned.id))
                for replica in (first, second)
            )
            == 1,
        )
        visible = first if first.transform_snapshots(spawned.id) else second
        hidden = second if visible is first else first
        assert hidden.transform_snapshots(spawned.id) == ()

        relevant.update(connections)
        spawned.entity.position = (5, 6, 7)
        stats = owner.flush_transforms(20)
        assert (stats.queued, stats.filtered) == (2, 0)
        with pytest.raises(ValueError, match="cannot decrease"):
            owner.flush_transforms(19)
        _pump(
            server,
            (first, second),
            lambda: all(
                replica.transform_snapshots(spawned.id)
                and replica.transform_snapshots(spawned.id)[-1].tick == 20
                for replica in (first, second)
            ),
        )
        assert visible.interpolate_transforms(15) == 1
        assert tuple(visible.objects[0].entity.position) == pytest.approx((3, 4, 5))
        assert hidden.interpolate_transforms(20) == 1
        assert tuple(hidden.objects[0].entity.position) == pytest.approx((5, 6, 7))

        owner.set_relevance_filter(None)
        late_client = network.Client(timeout=1, peer_timeout=2)
        late = replication.ClientReplication(late_client, Scene("late"), registry)
        late_client.connect("127.0.0.1", server.port)
        _pump(server, (first, second, late), lambda: late.is_synchronized)
        snapshots = late.transform_snapshots(spawned.id)
        assert len(snapshots) == 1
        assert (snapshots[0].sequence, snapshots[0].tick) == (2, 20)
        late.interpolate_transforms(20)
        assert tuple(late.objects[0].entity.position) == pytest.approx((5, 6, 7))
    finally:
        first.clear()
        second.clear()
        if late is not None:
            late.clear()
        for client in (first_client, second_client, late_client):
            if client is not None and client.connection is not None:
                client.disconnect("done")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_transform_api_bounds_and_root_exports() -> None:
    import easy3d

    registry = _registry()
    client = network.Client(timeout=1)
    with pytest.raises(ValueError, match=r"\[2, 256\]"):
        replication.ClientReplication(
            client, Scene("bad history"), registry, max_transform_samples=1
        )
    assert easy3d.TransformSnapshot is replication.TransformSnapshot
    assert easy3d.NetworkTransform is replication.NetworkTransform
    assert easy3d.TransformReplicationStats is replication.TransformReplicationStats
    assert easy3d.TransformFlushStats is replication.TransformFlushStats
