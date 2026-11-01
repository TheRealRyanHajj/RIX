"""Public physics components, immutable query hits, and contact snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .components import (
    Collider,
    ColliderShape,
    CollisionLayer,
    PhysicsMaterial,
    Rigidbody,
    RigidBodyType,
)
from .math import Quat, Vec3

if TYPE_CHECKING:
    from .entity import Entity
    from .scene import Scene


@dataclass(frozen=True, slots=True)
class PhysicsHit:
    entity: Entity
    point: Vec3
    normal: Vec3
    distance: float
    fraction: float


@dataclass(frozen=True, slots=True)
class CollisionEvent:
    """Per-recipient collision/trigger snapshot delivered after a fixed step."""

    other: Entity
    point: Vec3
    normal: Vec3


_LAYER_BITS: dict[str, int] = {
    "static": 1 << 0,
    "dynamic": 1 << 1,
    "sensor": 1 << 2,
    "character": 1 << 3,
}


def _query_options(
    scene: Scene,
    layers: Iterable[CollisionLayer] | None,
    include_triggers: bool,
    exclude: Entity | None,
) -> tuple[int, bool, object | None]:
    from .entity import Entity
    from .scene import Scene

    if not isinstance(scene, Scene):
        raise TypeError("scene must be an easy3d.Scene")
    if not isinstance(include_triggers, bool):
        raise TypeError("include_triggers must be a bool")
    if exclude is not None:
        if not isinstance(exclude, Entity):
            raise TypeError("exclude must be an easy3d.Entity or None")
        if exclude.scene is not scene:
            raise ValueError("excluded entity belongs to a different scene")
    mask = 0x0F
    if layers is not None:
        mask = 0
        for layer in layers:
            try:
                mask |= _LAYER_BITS[layer]
            except (KeyError, TypeError) as error:
                raise ValueError(
                    "layers must contain static, dynamic, sensor, or character"
                ) from error
    return mask, include_triggers, None if exclude is None else exclude._handle


def _convert_hits(scene: Scene, values: list[tuple[object, object, object, float, float]]) -> tuple[PhysicsHit, ...]:
    from .entity import Entity

    return tuple(
        PhysicsHit(Entity._from_handle(scene, handle), Vec3(point), Vec3(normal), distance, fraction)
        for handle, point, normal, distance, fraction in values
    )


def raycast_all(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> tuple[PhysicsHit, ...]:
    """Return all ray hits sorted nearest-first with stable entity-ID ties."""

    mask, triggers, excluded = _query_options(
        scene, layers, include_triggers, exclude
    )
    values = scene._native.physics_raycast_all(
        tuple(Vec3.from_value(origin)),
        tuple(Vec3.from_value(direction)),
        float(max_distance),
        mask,
        triggers,
        excluded,
    )
    return _convert_hits(scene, values)


def raycast(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> PhysicsHit | None:
    """Return the nearest ray hit, or ``None``."""

    hits = raycast_all(
        scene,
        origin,
        direction,
        max_distance,
        layers=layers,
        include_triggers=include_triggers,
        exclude=exclude,
    )
    return hits[0] if hits else None


def overlap_sphere(
    scene: Scene,
    center: Vec3 | tuple[float, float, float],
    radius: float,
    *,
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> tuple[PhysicsHit, ...]:
    """Return deduplicated overlaps sorted by generation-qualified entity ID."""

    mask, triggers, excluded = _query_options(
        scene, layers, include_triggers, exclude
    )
    values = scene._native.physics_overlap_sphere(
        tuple(Vec3.from_value(center)),
        float(radius),
        mask,
        triggers,
        excluded,
    )
    return _convert_hits(scene, values)


def overlap_box(
    scene: Scene,
    center: Vec3 | tuple[float, float, float],
    half_extents: Vec3 | tuple[float, float, float],
    *,
    rotation: Quat | Vec3 | tuple[float, float, float] = Quat(),
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> tuple[PhysicsHit, ...]:
    """Return deduplicated oriented-box overlaps sorted by entity ID."""

    mask, triggers, excluded = _query_options(
        scene, layers, include_triggers, exclude
    )
    quaternion = rotation if isinstance(rotation, Quat) else Quat.from_euler(rotation)
    values = scene._native.physics_overlap_box(
        tuple(Vec3.from_value(center)),
        tuple(Vec3.from_value(half_extents)),
        tuple(quaternion),
        mask,
        triggers,
        excluded,
    )
    return _convert_hits(scene, values)


def sphere_cast_all(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    radius: float,
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> tuple[PhysicsHit, ...]:
    """Sweep a sphere and return nearest-first immutable hits."""

    mask, triggers, excluded = _query_options(
        scene, layers, include_triggers, exclude
    )
    values = scene._native.physics_sphere_cast_all(
        tuple(Vec3.from_value(origin)),
        float(radius),
        tuple(Vec3.from_value(direction)),
        float(max_distance),
        mask,
        triggers,
        excluded,
    )
    return _convert_hits(scene, values)


def sphere_cast(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    radius: float,
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> PhysicsHit | None:
    hits = sphere_cast_all(
        scene,
        origin,
        radius,
        direction,
        max_distance,
        layers=layers,
        include_triggers=include_triggers,
        exclude=exclude,
    )
    return hits[0] if hits else None


def capsule_cast_all(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    radius: float,
    height: float,
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    rotation: Quat | Vec3 | tuple[float, float, float] = Quat(),
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> tuple[PhysicsHit, ...]:
    """Sweep a Y-axis capsule (total height) and return nearest-first hits."""

    mask, triggers, excluded = _query_options(
        scene, layers, include_triggers, exclude
    )
    quaternion = rotation if isinstance(rotation, Quat) else Quat.from_euler(rotation)
    values = scene._native.physics_capsule_cast_all(
        tuple(Vec3.from_value(origin)),
        float(radius),
        float(height),
        tuple(quaternion),
        tuple(Vec3.from_value(direction)),
        float(max_distance),
        mask,
        triggers,
        excluded,
    )
    return _convert_hits(scene, values)


def capsule_cast(
    scene: Scene,
    origin: Vec3 | tuple[float, float, float],
    radius: float,
    height: float,
    direction: Vec3 | tuple[float, float, float],
    max_distance: float,
    *,
    rotation: Quat | Vec3 | tuple[float, float, float] = Quat(),
    layers: Iterable[CollisionLayer] | None = None,
    include_triggers: bool = True,
    exclude: Entity | None = None,
) -> PhysicsHit | None:
    hits = capsule_cast_all(
        scene,
        origin,
        radius,
        height,
        direction,
        max_distance,
        rotation=rotation,
        layers=layers,
        include_triggers=include_triggers,
        exclude=exclude,
    )
    return hits[0] if hits else None

__all__ = [
    "Collider",
    "ColliderShape",
    "CollisionLayer",
    "CollisionEvent",
    "PhysicsHit",
    "PhysicsMaterial",
    "Rigidbody",
    "RigidBodyType",
    "capsule_cast",
    "capsule_cast_all",
    "overlap_box",
    "overlap_sphere",
    "raycast",
    "raycast_all",
    "sphere_cast",
    "sphere_cast_all",
]
