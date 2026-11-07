"""Explicit low-level APIs retained for advanced RIX projects."""

from .assets import ModelCache, TextureCache
from .components import (
    CharacterController,
    Collider,
    CullMode,
    LightComponent,
    MeshRenderer,
    PhysicsMaterial,
    Rigidbody,
)
from .game import CallbackHandle, RendererStats
from .math import Quat, Vec2, Vec3
from .physics import CollisionEvent, Constraint, PhysicsHit
from .scheduler import CallbackStats, SchedulerStats

__all__ = [
    "CallbackHandle",
    "CallbackStats",
    "CharacterController",
    "Collider",
    "CullMode",
    "CollisionEvent",
    "Constraint",
    "LightComponent",
    "MeshRenderer",
    "ModelCache",
    "PhysicsHit",
    "PhysicsMaterial",
    "Quat",
    "RendererStats",
    "Rigidbody",
    "SchedulerStats",
    "TextureCache",
    "Vec2",
    "Vec3",
]
