"""Finite cooperative/competitive authoritative arena scenarios."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from typing import Literal

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


ArenaMode = Literal["cooperative", "competitive"]
PLAYER = 1
MATCH = 2
OBJECTIVE = 3
HEALTH = 1
TEAM = 2
SCORE = 3
ATTACK = 1
ASSIGNED = 2
DAMAGE = 25


@dataclass(frozen=True, slots=True)
class ArenaResult:
    mode: ArenaMode
    clients: int
    phase: MatchPhase
    winning_score: int
    damage_events: int
    objective_destroyed: bool
    eliminated_players: int


def _server(on_connect, on_disconnect) -> Server:  # type: ignore[no-untyped-def]
    for port in range(33000, 33100):
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
    raise RuntimeError("no loopback arena port is available")


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
        raise RuntimeError("arena scenario timed out")


def run_arena(mode: ArenaMode = "cooperative", client_count: int = 2) -> ArenaResult:
    if mode not in ("cooperative", "competitive"):
        raise ValueError("mode must be 'cooperative' or 'competitive'")
    if isinstance(client_count, bool) or not isinstance(client_count, int):
        raise TypeError("client_count must be an integer")
    if not 2 <= client_count <= 8:
        raise ValueError("client_count must be in [2, 8]")

    assignments: dict[str, replication.NetworkObjectId] = {}
    players: dict[network.ConnectionId, replication.NetworkObjectId] = {}
    owner_box: list[replication.ServerReplication] = []
    match_box: list[ServerMatchState] = []
    damage_events = 0

    def assigned(entity: Entity, object_value: object) -> None:
        assignments[entity.scene.name] = replication.NetworkObjectId(int(object_value))

    def attack(
        attacker: Entity,
        _sender: network.ConnectionId,
        target_value: object,
    ) -> None:
        nonlocal damage_events
        match = match_box[0]
        if match.phase is not MatchPhase.PLAYING:
            return
        owner = owner_box[0]
        target_id = replication.NetworkObjectId(int(target_value))
        target = next((item for item in owner.objects if item.id == target_id), None)
        attacker_item = next((item for item in owner.objects if item.entity == attacker), None)
        if target is None or attacker_item is None or target.id == attacker_item.id:
            return
        if (target.entity.position - attacker.position).length_squared > 36.0:
            return
        if mode == "cooperative":
            if target.prefab_id.value != OBJECTIVE:
                return
        else:
            if target.prefab_id.value != PLAYER:
                return
            if owner.variable(target.id, TEAM).value == owner.variable(attacker_item.id, TEAM).value:
                return
        health = owner.variable(target.id, HEALTH)
        if int(health.value) <= 0:
            return
        health.value = max(0, int(health.value) - DAMAGE)
        damage_events += 1
        if health.value == 0:
            if mode == "cooperative":
                for player_id in players.values():
                    score = owner.variable(player_id, SCORE)
                    score.value = int(score.value) + 1
                owner.despawn(target.id)
            else:
                score = owner.variable(attacker_item.id, SCORE)
                score.value = int(score.value) + 1
            owner.flush()
            match.finish_round(2, intermission_ticks=1, match_over=True)
        else:
            owner.flush()

    registry = replication.PrefabRegistry(schema_version=15)
    registry.register(PLAYER, "arena_player", lambda scene: Entity("player", scene=scene))
    registry.register_variable(PLAYER, HEALTH, "health", "int", 100, max_bytes=8)
    registry.register_variable(PLAYER, TEAM, "team", "int", 0, max_bytes=8)
    registry.register_variable(PLAYER, SCORE, "score", "int", 0, max_bytes=8)
    registry.register_transform(PLAYER)
    registry.register_rpc(
        PLAYER,
        ATTACK,
        "request_attack",
        "client_to_server",
        (("int", 8),),
        attack,
        reliable=True,
        rate_limit=16,
        require_owner=True,
    )
    registry.register_rpc(
        PLAYER,
        ASSIGNED,
        "assigned_player",
        "server_to_client",
        (("int", 8),),
        assigned,
        reliable=True,
        rate_limit=8,
    )
    registry.register(MATCH, "match", lambda scene: Entity("match", scene=scene))
    register_match_state(registry, MATCH)
    registry.register(OBJECTIVE, "objective", lambda scene: Entity("objective", scene=scene))
    registry.register_variable(OBJECTIVE, HEALTH, "health", "int", 100, max_bytes=8)

    def connected(server: Server, connection: network.ConnectionId) -> None:
        owner = owner_box[0]
        player = owner.spawn(PLAYER)
        index = len(players)
        player.entity.position = (float(index), 0.0, 0.0)
        owner.variable(player.id, TEAM).value = 0 if mode == "cooperative" else index
        owner.flush()
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        if owner.call_client(connection, player.id, ASSIGNED, player.id.value) is not network.SendStatus.QUEUED:
            server.disconnect(connection, "arena assignment backpressure")

    def disconnected(_server: Server, event: network.NetworkEvent) -> None:
        identifier = players.pop(event.connection, None)
        if identifier is not None and any(item.id == identifier for item in owner_box[0].objects):
            owner_box[0].despawn(identifier)

    server = _server(connected, disconnected)
    server.load_scene(Scene("arena authority"))
    owner = replication.ServerReplication(server, registry, max_objects=32)
    owner_box.append(owner)
    match_object = owner.spawn(MATCH)
    match = ServerMatchState(owner, match_object.id, countdown_ticks=1)
    match_box.append(match)
    objective = owner.spawn(OBJECTIVE) if mode == "cooperative" else None
    if objective is not None:
        objective.entity.position = (2.0, 0.0, 0.0)

    clients: list[network.Client] = []
    mirrors: list[replication.ClientReplication] = []
    try:
        for index in range(client_count):
            client = network.Client(timeout=1, peer_timeout=2)
            mirror = replication.ClientReplication(
                client, Scene(f"arena client {index}"), registry, max_objects=32
            )
            clients.append(client)
            mirrors.append(mirror)
            client.connect("127.0.0.1", server.port)
        expected_objects = client_count + 1 + (1 if objective is not None else 0)
        _pump(
            server,
            mirrors,
            lambda: all(mirror.is_synchronized for mirror in mirrors)
            and len(assignments) == client_count
            and all(len(mirror.objects) == expected_objects for mirror in mirrors),
        )

        match.start_match(0, countdown_ticks=1)
        _pump(
            server,
            mirrors,
            lambda: all(
                ClientMatchState(mirror, match_object.id).phase is MatchPhase.COUNTDOWN
                for mirror in mirrors
            ),
        )
        match.advance(1)
        _pump(
            server,
            mirrors,
            lambda: all(
                ClientMatchState(mirror, match_object.id).phase is MatchPhase.PLAYING
                for mirror in mirrors
            ),
        )

        ordered_players = list(players.values())
        if mode == "cooperative":
            assert objective is not None
            attackers = [
                assignments[mirror.objects[0].entity.scene.name]
                for mirror in mirrors
            ]
            for index in range(4):
                mirror = mirrors[index % len(mirrors)]
                attacker_id = attackers[index % len(mirrors)]
                mirror.call_server(attacker_id, ATTACK, objective.id.value)
        else:
            attacker_id = ordered_players[0]
            target_id = ordered_players[1]
            attacker_mirror = next(
                mirror
                for mirror in mirrors
                if assignments[mirror.objects[0].entity.scene.name] == attacker_id
            )
            for _ in range(4):
                attacker_mirror.call_server(attacker_id, ATTACK, target_id.value)

        _pump(
            server,
            mirrors,
            lambda: all(
                ClientMatchState(mirror, match_object.id).phase is MatchPhase.MATCH_END
                for mirror in mirrors
            ),
        )
        scores = [int(owner.variable(identifier, SCORE).value) for identifier in players.values()]
        eliminated = sum(
            int(owner.variable(identifier, HEALTH).value) == 0
            for identifier in players.values()
        )
        return ArenaResult(
            mode,
            client_count,
            match.phase,
            max(scores),
            damage_events,
            objective is not None
            and not any(item.id == objective.id for item in owner.objects),
            eliminated,
        )
    finally:
        for mirror in mirrors:
            mirror.clear()
        for client in clients:
            if client.connection is not None:
                client.disconnect("arena complete")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cooperative", "competitive"), default="cooperative")
    parser.add_argument("--clients", type=int, choices=range(2, 9), default=2)
    args = parser.parse_args()
    result = run_arena(args.mode, args.clients)
    print(
        f"arena complete: mode={result.mode} clients={result.clients} "
        f"phase={result.phase.name} winning_score={result.winning_score} "
        f"damage_events={result.damage_events} objective_destroyed={result.objective_destroyed} "
        f"eliminated_players={result.eliminated_players}"
    )


if __name__ == "__main__":
    main()
