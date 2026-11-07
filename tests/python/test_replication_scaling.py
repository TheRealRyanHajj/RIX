from __future__ import annotations

import time

import pytest

from rix import Entity, Scene
from rix.net import (
    Client,
    ClientReplication,
    NetworkError,
    NetworkObjectId,
    PrefabRegistry,
    Server,
    ServerReplication,
    SpatialInterest,
)
from rix.net import replication


def _registry() -> PrefabRegistry:
    registry = PrefabRegistry(schema_version=14)
    registry.register(1, "actor", lambda scene: Entity("actor", scene=scene))
    registry.register_transform(1)
    return registry


def _server() -> Server:
    for port in range(32900, 33000):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind scaling replication test server")


def _pump(server: Server, mirror: ClientReplication, predicate) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not predicate():
        server.poll()
        mirror.poll()
        time.sleep(0.001)
    assert predicate()


def test_transform_ack_batches_are_bounded_and_exactly_framed() -> None:
    identifier = NetworkObjectId(1)
    with pytest.raises(ValueError, match="count"):
        replication._transform_ack_batch_frame(())
    with pytest.raises(ValueError, match="count"):
        replication._transform_ack_batch_frame(
            tuple((identifier, sequence) for sequence in range(257))
        )

    frame = replication._transform_ack_batch_frame(
        ((identifier, 3), (NetworkObjectId(2), 4))
    )
    message_type, payload = replication._decode(frame)
    assert message_type == replication._TRANSFORM_ACK_BATCH
    assert len(payload) == (
        replication._TRANSFORM_ACK_BATCH_PREFIX.size
        + 2 * replication._TRANSFORM_ACK_PAYLOAD.size
    )


def test_acknowledged_transform_deltas_recover_a_missing_baseline() -> None:
    server = _server()
    server.load_scene(Scene("delta authority"))
    registry = _registry()
    owner = ServerReplication(server, registry)
    actor = owner.spawn(1)
    client = Client(timeout=1, peer_timeout=2)
    mirror = ClientReplication(client, Scene("delta mirror"), registry)
    try:
        client.connect("127.0.0.1", server.port)
        _pump(server, mirror, lambda: mirror.is_synchronized)
        connection = server.connections[0]
        _pump(server, mirror, lambda: (connection, actor.id) in owner._transform_baselines)

        actor.entity.position = (0.5, 0.0, 0.0)
        first = owner.flush_transforms(1)
        assert (first.full_snapshots, first.delta_snapshots) == (0, 1)
        assert first.bytes_queued == (
            replication._HEADER.size + replication._TRANSFORM_DELTA_PAYLOAD.size
        )
        _pump(server, mirror, lambda: mirror.delta_baseline_stats.delta_received >= 1)
        _pump(
            server,
            mirror,
            lambda: owner._transform_baselines[(connection, actor.id)].sequence == 1,
        )

        mirror._transform_history[actor.id].clear()
        actor.entity.position = (1.0, 0.0, 0.0)
        second = owner.flush_transforms(2)
        assert second.delta_snapshots == 1
        _pump(server, mirror, lambda: mirror.delta_baseline_stats.recovery_requests == 1)
        _pump(server, mirror, lambda: (connection, actor.id) not in owner._transform_baselines)
        actor.entity.position = (1.5, 0.0, 0.0)
        recovered = owner.flush_transforms(3)
        assert (recovered.full_snapshots, recovered.delta_snapshots) == (1, 0)
        _pump(
            server,
            mirror,
            lambda: mirror.transform_snapshots(actor.id)
            and mirror.transform_snapshots(actor.id)[-1].sequence == 3,
        )
        assert mirror.transform_snapshots(actor.id)[-1].position.x == pytest.approx(1.5)
        with pytest.raises(ValueError, match="future"):
            owner._receive_transform_ack(
                connection,
                replication._TRANSFORM_ACK_PAYLOAD.pack(
                    actor.id.value, owner.last_transform_flush.sequence + 1
                ),
            )
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("done")
            client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_spatial_interest_priority_and_budget_bound_replaceable_work() -> None:
    server = _server()
    server.load_scene(Scene("interest authority"))
    registry = _registry()
    interest = SpatialInterest(radius=5.0)
    owner = ServerReplication(
        server,
        registry,
        spatial_interest=interest,
        priority=lambda _connection, item: float(item.entity.name == "preferred"),
        transform_budget_bytes_per_second=1024,
        transform_budget_burst_bytes=76,
        transform_tick_rate=60,
    )
    ordinary = owner.spawn(1)
    ordinary.entity.name = "ordinary"
    ordinary.entity.position = (2.0, 0.0, 0.0)
    preferred = owner.spawn(1)
    preferred.entity.name = "preferred"
    preferred.entity.position = (1.0, 0.0, 0.0)
    distant = owner.spawn(1)
    distant.entity.name = "distant"
    distant.entity.position = (20.0, 0.0, 0.0)
    client = Client(timeout=1, peer_timeout=2)
    mirror = ClientReplication(client, Scene("interest mirror"), registry)
    try:
        client.connect("127.0.0.1", server.port)
        _pump(server, mirror, lambda: mirror.is_synchronized)
        connection = server.connections[0]
        interest.set_observer(connection, (0.0, 0.0, 0.0))
        stats = owner.flush_transforms(1)
        assert stats.queued == 1
        assert stats.filtered == 1
        assert stats.budget_deferred == 1
        assert stats.bytes_queued == 76
        _pump(server, mirror, lambda: bool(mirror.transform_snapshots(preferred.id)))
        assert mirror.transform_snapshots(ordinary.id) == ()
        assert mirror.transform_snapshots(distant.id) == ()
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("done")
            client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)
