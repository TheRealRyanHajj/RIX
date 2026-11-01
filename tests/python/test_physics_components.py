from __future__ import annotations

import math

import pytest

from easy3d import (
    Collider,
    Entity,
    PhysicsError,
    PhysicsMaterial,
    Rigidbody,
    Scene,
    Vec3,
)


def test_collider_rigidbody_material_and_fixed_sync() -> None:
    scene = Scene("physics")
    floor = Entity("floor", scene=scene)
    floor.position = (0.0, -0.5, 0.0)
    floor_collider = floor.add_component(
        Collider,
        shape="box",
        half_extents=(5.0, 0.5, 5.0),
        material=PhysicsMaterial(friction=0.8, restitution=0.0),
    )
    assert floor_collider.material.friction == pytest.approx(0.8)
    assert floor_collider.material.restitution == pytest.approx(0.0)

    ball = Entity("ball", scene=scene)
    ball.position = (0.0, 3.0, 0.0)
    collider = ball.add_component(
        Collider,
        shape="sphere",
        radius=0.5,
        material=PhysicsMaterial(friction=0.3, restitution=0.1),
    )
    body = ball.add_component(Rigidbody, mass=2.0)

    assert ball.get_component(Collider) is not None
    assert ball.get_component(Rigidbody) is not None
    assert collider.shape == "sphere"
    assert collider.radius == pytest.approx(0.5)
    assert body.mass == pytest.approx(2.0)
    assert body.body_type == "dynamic"

    with pytest.raises(PhysicsError, match="physics-owned"):
        ball.position = (0.0, 10.0, 0.0)

    body.add_impulse((2.0, 0.0, 0.0))
    for _ in range(240):
        scene._native.step_physics(1.0 / 60.0)

    assert ball.position.y == pytest.approx(0.5, abs=0.08)
    assert ball.position.x > 0.1
    assert all(math.isfinite(value) for value in body.linear_velocity)


def test_trigger_configuration_velocity_force_and_teleport_safety() -> None:
    scene = Scene()
    entity = Entity(scene=scene)
    collider = entity.add_component(
        Collider,
        shape="box",
        trigger=True,
        layer="sensor",
        material=PhysicsMaterial(friction=0.0, restitution=1.0),
    )
    body = entity.add_component(Rigidbody, mass=1.0, use_gravity=False)
    assert collider.is_trigger
    assert collider.layer == "sensor"
    assert not body.use_gravity

    body.linear_velocity = (1.0, 0.0, 0.0)
    body.add_force((2.0, 0.0, 0.0))
    scene._native.step_physics(0.5)
    assert entity.position.x > 0.5

    body.teleport((4.0, 5.0, 6.0), (0.0, 90.0, 0.0))
    assert entity.position.almost_equal(Vec3(4.0, 5.0, 6.0))
    assert entity.rotation.y == pytest.approx(90.0, abs=1.0e-3)

    with pytest.raises(PhysicsError, match="cannot be parented"):
        entity.parent = Entity(scene=scene)

    body.remove()
    assert not entity.has_component(Rigidbody)
    entity.position = (1.0, 2.0, 3.0)
    collider.remove()
    assert not entity.has_component(Collider)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda entity: Collider(entity, radius=0.0), "radius"),
        (lambda entity: Collider(entity, half_extents=(1.0, 0.0, 1.0)), "extents"),
        (lambda entity: Rigidbody(entity, mass=float("nan")), "mass"),
    ],
)
def test_physics_component_validation(factory: object, message: str) -> None:
    entity = Entity(scene=Scene())
    if "mass" in message:
        entity.add_component(Collider)
    with pytest.raises(ValueError, match=message):
        factory(entity)  # type: ignore[operator]


def test_destroy_entity_releases_native_body_and_invalidates_facades() -> None:
    scene = Scene()
    entity = Entity(scene=scene)
    collider = entity.add_component(Collider)
    body = entity.add_component(Rigidbody)
    entity.destroy()

    assert not entity.is_alive
    with pytest.raises(ReferenceError):
        _ = collider.shape
    with pytest.raises(ReferenceError):
        _ = body.mass
