"""Public physics types.

Queries and collision event snapshots are added in Phase 2.6. This module
currently exposes the Phase 2.5 body, collider, material, and layer contracts.
"""

from .components import (
    Collider,
    ColliderShape,
    CollisionLayer,
    PhysicsMaterial,
    Rigidbody,
    RigidBodyType,
)

__all__ = [
    "Collider",
    "ColliderShape",
    "CollisionLayer",
    "PhysicsMaterial",
    "Rigidbody",
    "RigidBodyType",
]
