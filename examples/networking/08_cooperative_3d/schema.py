from __future__ import annotations

import math

import rix
from rix import net


PLAYER = 1
OBJECTIVE = 2
ASSIGNED = 1
MOVE = 2


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
    entity.position += rix.Vec3(x, 0, z) * (4.0 / 60.0)


def registry() -> net.PrefabRegistry:
    result = net.PrefabRegistry(schema_version=108)
    result.register(
        PLAYER,
        "coop_player",
        lambda scene: rix.Cube(
            scene=scene,
            color="#38bdf8",
            size=0.8,
            collider=False,
        ),
    )
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
    result.register(
        OBJECTIVE,
        "shared_objective",
        lambda scene: rix.Sphere(
            scene=scene,
            color="orange",
            radius=0.65,
            collider=False,
        ),
    )
    result.register_transform(OBJECTIVE)
    return result
