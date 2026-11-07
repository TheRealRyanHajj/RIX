from __future__ import annotations

import rix
from rix import net


PLAYER = 1
HEALTH = 1
SCORE = 2
ASSIGNED = 1
DAMAGE = 2

_authority: net.ServerReplication | None = None


def set_authority(authority: net.ServerReplication) -> None:
    global _authority
    _authority = authority


def _assigned(entity: rix.Entity, object_id: object) -> None:
    entity.network_local_id = int(object_id)  # type: ignore[attr-defined]


def _damage(
    attacker: rix.Entity,
    _sender: net.ConnectionId,
    target_value: object,
) -> None:
    authority = _authority
    if authority is None:
        return
    target_id = net.NetworkObjectId(int(target_value))
    target = next((item for item in authority.objects if item.id == target_id), None)
    attacker_item = next(
        (item for item in authority.objects if item.entity is attacker), None
    )
    if target is None or attacker_item is None or target.id == attacker_item.id:
        return
    health = authority.variable(target.id, HEALTH)
    health.value = max(0, int(health.value) - 20)
    if health.value == 0:
        score = authority.variable(attacker_item.id, SCORE)
        score.value = int(score.value) + 1
        health.value = 100
    authority.flush()


def registry() -> net.PrefabRegistry:
    result = net.PrefabRegistry(schema_version=110)
    result.register(PLAYER, "score_player", lambda scene: rix.Entity("player", scene=scene))
    result.register_variable(PLAYER, HEALTH, "health", "int", 100, max_bytes=8)
    result.register_variable(PLAYER, SCORE, "score", "int", 0, max_bytes=8)
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
        DAMAGE,
        "request_damage",
        "client_to_server",
        (("int", 8),),
        _damage,
        rate_limit=5,
        require_owner=True,
    )
    return result
