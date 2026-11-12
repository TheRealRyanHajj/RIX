"""Python module for the RIX example in examples/networking/09_authoritative_fps.

This module defines the shared message/state schema imported by the neighboring client
and server examples. Follow the adjacent README to run the example."""

from __future__ import annotations

import math

import rix
from rix import net


PLAYER = 1
MATCH = 2
HEALTH = 1
SCORE = 2
ASSIGNED = 1
MOVE = 2
SHOOT = 3
DAMAGE = 25

_authority: net.ServerReplication | None = None
_match: net.ServerMatchState | None = None


def set_authority(
    authority: net.ServerReplication, match: net.ServerMatchState
) -> None:
    global _authority, _match
    _authority = authority
    _match = match


def _assigned(entity: rix.Entity, object_id: object) -> None:
    entity.network_local_id = int(object_id)  # type: ignore[attr-defined]


def _move(
    entity: rix.Entity,
    _sender: net.ConnectionId,
    x_value: object,
    z_value: object,
) -> None:
    x, z = float(x_value), float(z_value)
    length = math.hypot(x, z)
    if not math.isfinite(length) or length > 1.01:
        return
    entity.position += rix.Vec3(x, 0, z) * (5.0 / 60.0)
    entity.position = (
        min(14.0, max(-14.0, entity.position.x)),
        0.8,
        min(14.0, max(-14.0, entity.position.z)),
    )


def _shoot(
    attacker: rix.Entity,
    _sender: net.ConnectionId,
    x_value: object,
    y_value: object,
    z_value: object,
) -> None:
    authority, match = _authority, _match
    if authority is None or match is None or match.phase is not net.MatchPhase.PLAYING:
        return
    direction = rix.Vec3(float(x_value), float(y_value), float(z_value))
    if not 0.99 <= direction.length <= 1.01:
        return
    direction = direction.normalized()
    origin = attacker.position + rix.Vec3(0, 0.2, 0)
    best: tuple[float, net.ReplicatedObject] | None = None
    for item in authority.objects:
        if item.prefab_id.value != PLAYER or item.entity is attacker:
            continue
        offset = item.entity.position - origin
        distance = offset.dot(direction)
        if not 0 < distance <= 30:
            continue
        closest = origin + direction * distance
        if (item.entity.position - closest).length_squared <= 0.8**2:
            if best is None or distance < best[0]:
                best = (distance, item)
    if best is None:
        return
    target = best[1]
    health = authority.variable(target.id, HEALTH)
    health.value = max(0, int(health.value) - DAMAGE)
    if health.value == 0:
        attacker_item = next(
            item for item in authority.objects if item.entity is attacker
        )
        score = authority.variable(attacker_item.id, SCORE)
        score.value = int(score.value) + 1
        health.value = 100
        target.entity.position = (-target.entity.position.x, 0.8, -target.entity.position.z)
    authority.flush()


def registry() -> net.PrefabRegistry:
    result = net.PrefabRegistry(schema_version=109)
    result.register(
        PLAYER,
        "fps_player",
        lambda scene: rix.Cube(
            scene=scene,
            color="#38bdf8",
            size=(0.8, 1.6, 0.8),
            collider=False,
        ),
    )
    result.register_variable(PLAYER, HEALTH, "health", "int", 100, max_bytes=8)
    result.register_variable(PLAYER, SCORE, "score", "int", 0, max_bytes=8)
    result.register_transform(PLAYER)
    result.register_rpc(
        PLAYER,
        ASSIGNED,
        "assigned_player",
        "server_to_client",
        (("int", 8),),
        _assigned,
        rate_limit=8,
    )
    result.register_rpc(
        PLAYER,
        MOVE,
        "request_move",
        "client_to_server",
        (("float", 8), ("float", 8)),
        _move,
        reliable=False,
        rate_limit=90,
        require_owner=True,
    )
    result.register_rpc(
        PLAYER,
        SHOOT,
        "request_shoot",
        "client_to_server",
        (("float", 8), ("float", 8), ("float", 8)),
        _shoot,
        reliable=True,
        rate_limit=12,
        require_owner=True,
    )
    result.register(MATCH, "match", lambda scene: rix.Entity("match", scene=scene))
    net.register_match_state(result, MATCH)
    return result
