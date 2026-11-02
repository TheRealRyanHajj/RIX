from __future__ import annotations

import time

import pytest

from easy3d import (
    ClientMatchState,
    Entity,
    MatchPhase,
    NetworkError,
    Scene,
    Server,
    ServerMatchState,
    network,
    register_match_state,
    replication,
)


def _registry() -> replication.PrefabRegistry:
    registry = replication.PrefabRegistry(schema_version=11)
    registry.register(1, "match", lambda scene: Entity("match", scene=scene))
    register_match_state(registry, 1)
    return registry


def _server() -> Server:
    for port in range(32800, 32900):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=2)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind match-state test server")


def _pump(server: Server, mirrors: tuple[replication.ClientReplication, ...], predicate) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and not predicate():
        server.poll()
        for mirror in mirrors:
            mirror.poll()
        time.sleep(0.001)
    assert predicate()


def test_match_state_timer_transitions_and_late_join() -> None:
    server = _server()
    server.load_scene(Scene("match authority"))
    registry = _registry()
    owner = replication.ServerReplication(server, registry)
    spawned = owner.spawn(1)
    match = ServerMatchState(owner, spawned.id, countdown_ticks=3)
    first_client = network.Client(timeout=1, peer_timeout=2)
    first_replication = replication.ClientReplication(
        first_client, Scene("first match client"), registry
    )
    late_client: network.Client | None = None
    late_replication: replication.ClientReplication | None = None
    try:
        first_client.connect("127.0.0.1", server.port)
        _pump(server, (first_replication,), lambda: first_replication.is_synchronized)
        first = ClientMatchState(first_replication, spawned.id)
        assert (first.phase, first.round, first.deadline_tick, first.revision) == (
            MatchPhase.WAITING,
            0,
            None,
            0,
        )

        assert match.start_match(100) == 4
        _pump(server, (first_replication,), lambda: first.revision == 1)
        assert (first.phase, first.round, first.deadline_tick) == (
            MatchPhase.COUNTDOWN,
            1,
            103,
        )
        assert first.remaining_ticks(101) == 2
        assert not match.advance(102)

        late_client = network.Client(timeout=1, peer_timeout=2)
        late_replication = replication.ClientReplication(
            late_client, Scene("late match client"), registry
        )
        late_client.connect("127.0.0.1", server.port)
        _pump(server, (first_replication, late_replication), lambda: late_replication.is_synchronized)
        late = ClientMatchState(late_replication, spawned.id)
        assert (late.phase, late.round, late.deadline_tick, late.revision) == (
            MatchPhase.COUNTDOWN,
            1,
            103,
            1,
        )

        assert match.advance(103)
        _pump(server, (first_replication, late_replication), lambda: late.revision == 2)
        assert first.phase is late.phase is MatchPhase.PLAYING
        with pytest.raises(RuntimeError, match="only while"):
            match.start_match(104)

        assert match.finish_round(110, intermission_ticks=2) == 3
        _pump(server, (first_replication, late_replication), lambda: late.revision == 3)
        assert late.phase is MatchPhase.ROUND_END and late.deadline_tick == 112
        assert match.advance(112)
        _pump(server, (first_replication, late_replication), lambda: late.revision == 4)
        assert (late.phase, late.round, late.deadline_tick) == (
            MatchPhase.COUNTDOWN,
            2,
            115,
        )
        assert match.advance(115)
        match.finish_round(120, intermission_ticks=1, match_over=True)
        _pump(server, (first_replication, late_replication), lambda: late.revision == 6)
        assert late.phase is MatchPhase.MATCH_END and late.deadline_tick is None
        match.reset(121)
        _pump(server, (first_replication, late_replication), lambda: late.revision == 7)
        assert (late.phase, late.round, late.deadline_tick) == (
            MatchPhase.WAITING,
            0,
            None,
        )
        with pytest.raises(ValueError, match="cannot decrease"):
            match.advance(120)
    finally:
        first_replication.clear()
        if late_replication is not None:
            late_replication.clear()
        for client in (first_client, late_client):
            if client is not None and client.connection is not None:
                client.disconnect("done")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def test_match_schema_and_authority_guards() -> None:
    registry = _registry()
    fields = registry.variables(1)
    assert [field.name for field in fields] == [
        "match_phase",
        "match_round",
        "match_deadline_tick",
        "match_revision",
    ]
    client = network.Client(timeout=1)
    mirror = replication.ClientReplication(client, Scene("read only"), registry)
    with pytest.raises(TypeError, match="ServerReplication"):
        ServerMatchState(mirror, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("target", tuple(MatchPhase))
def test_late_join_receives_every_match_phase(target: MatchPhase) -> None:
    server = _server()
    server.load_scene(Scene(f"authority {target.name}"))
    registry = _registry()
    owner = replication.ServerReplication(server, registry)
    spawned = owner.spawn(1)
    match = ServerMatchState(owner, spawned.id, countdown_ticks=2)
    client = network.Client(timeout=1, peer_timeout=2)
    mirror = replication.ClientReplication(client, Scene(f"client {target.name}"), registry)
    try:
        if target is not MatchPhase.WAITING:
            match.start_match(10)
        if target in (MatchPhase.PLAYING, MatchPhase.ROUND_END, MatchPhase.MATCH_END):
            match.advance(12)
        if target is MatchPhase.ROUND_END:
            match.finish_round(13, intermission_ticks=2)
        elif target is MatchPhase.MATCH_END:
            match.finish_round(13, intermission_ticks=1, match_over=True)
        client.connect("127.0.0.1", server.port)
        _pump(server, (mirror,), lambda: mirror.is_synchronized)
        view = ClientMatchState(mirror, spawned.id)
        assert view.phase is target
        assert view.revision == {
            MatchPhase.WAITING: 0,
            MatchPhase.COUNTDOWN: 1,
            MatchPhase.PLAYING: 2,
            MatchPhase.ROUND_END: 3,
            MatchPhase.MATCH_END: 3,
        }[target]
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("done")
            client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)
