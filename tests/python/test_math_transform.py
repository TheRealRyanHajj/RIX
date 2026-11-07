from __future__ import annotations

import math

import pytest

from rix import Entity, Quat, Scene, Vec2, Vec3


def test_vec2_and_vec3_value_operations() -> None:
    assert Vec2((1, 2)) + Vec2(3, 4) == Vec2(4, 6)
    assert Vec3((1, 2, 3)) - Vec3(1, 1, 1) == Vec3(0, 1, 2)
    assert Vec3(1, 0, 0).cross(Vec3(0, 1, 0)) == Vec3(0, 0, 1)
    assert Vec3(3, 4, 0).normalized().almost_equal(Vec3(0.6, 0.8, 0))
    assert Vec3(1.0, 1.0, 1.0) != Vec3(1.0 + 1.0e-9, 1.0, 1.0)
    assert Vec3(1.0, 1.0, 1.0).almost_equal(Vec3(1.0 + 1.0e-9, 1.0, 1.0))

    with pytest.raises(ValueError, match="zero-length"):
        Vec3().normalized()
    with pytest.raises(ValueError, match="finite"):
        Vec3(math.inf, 0, 0)
    with pytest.raises(ZeroDivisionError):
        _ = Vec2(1, 2) / 0


def test_quaternion_euler_facade_and_rotation() -> None:
    yaw = Quat.from_euler((0, 90, 0))
    assert yaw.rotate((0, 0, -1)).almost_equal(Vec3(-1, 0, 0), tolerance=1.0e-5)
    assert yaw.almost_equal(Quat.from_euler(yaw.to_euler()), tolerance=1.0e-5)
    assert Quat().normalized() == Quat()
    with pytest.raises(ValueError, match="zero-length"):
        Quat(0, 0, 0, 0).normalized()


def test_entity_vector_properties_are_live_native_proxies() -> None:
    scene = Scene("live vectors")
    entity = scene.create_entity()
    entity.position = (1, 2, 3)
    position = entity.position
    position.x += 4
    position.y = -2
    assert entity.position == Vec3(5, -2, 3)

    entity.scale = Vec3(2, 3, 4)
    entity.scale.z *= 2
    assert entity.scale == Vec3(2, 3, 8)

    entity.rotation = (0, 90, 0)
    assert entity.quaternion.almost_equal(Quat.from_euler((0, 90, 0)))
    entity.rotation.y += 45
    assert entity.quaternion.almost_equal(Quat.from_euler((0, 135, 0)), tolerance=1.0e-5)

    with pytest.raises(ValueError, match="nonzero"):
        entity.scale = (1, 0, 1)


def test_incremental_euler_rotation_crosses_singularities_and_full_turns() -> None:
    scene = Scene("continuous Euler rotation")
    entity = scene.create_entity()
    entity.rotation = (10, 0, 20)

    for _ in range(400):
        entity.ry += 1

    assert entity.rotation.almost_equal(Vec3(10, 400, 20), tolerance=1.0e-5)
    assert entity.quaternion.almost_equal(
        Quat.from_euler((10, 400, 20)),
        tolerance=1.0e-5,
    )

    # Rotation hints belong to the native entity, not to one Python wrapper.
    alias = scene.entities[0]
    alias.ry += 20
    assert entity.ry == pytest.approx(420)


def test_hierarchy_world_transform_dirty_propagation_and_cycle_rejection() -> None:
    scene = Scene("hierarchy")
    parent = scene.create_entity("parent")
    child = scene.create_entity("child")
    grandchild = scene.create_entity("grandchild")

    parent.position = (10, 0, 0)
    child.position = (1, 2, 3)
    grandchild.position = (0, 1, 0)
    child.parent = parent
    grandchild.parent = child

    assert child.parent == parent
    assert parent.children == (child,)
    assert grandchild.world_position.almost_equal(Vec3(11, 3, 3))

    # The previous read populated native caches. A parent mutation must dirty descendants.
    parent.position.x = 20
    assert grandchild.world_position.almost_equal(Vec3(21, 3, 3))

    with pytest.raises(ValueError, match="cycle"):
        parent.parent = grandchild
    with pytest.raises(ValueError, match="itself"):
        parent.parent = parent


def test_parent_rotation_and_scale_affect_world_transform() -> None:
    scene = Scene("rotation and scale")
    parent = scene.create_entity("parent")
    child = scene.create_entity("child")
    parent.position = (3, 0, 0)
    parent.rotation = (0, 90, 0)
    parent.scale = (2, 2, 2)
    child.position = (0, 0, -1)
    child.parent = parent

    assert child.world_position.almost_equal(Vec3(1, 0, 0), tolerance=1.0e-5)
    assert child.world_quaternion.almost_equal(Quat.from_euler((0, 90, 0)))
    assert child.world_scale.almost_equal(Vec3(2, 2, 2))


def test_reparent_keep_world_and_parent_destruction_preserve_world_transform() -> None:
    scene = Scene("reparent")
    first_parent = scene.create_entity("first")
    second_parent = scene.create_entity("second")
    child = scene.create_entity("child")
    first_parent.position = (10, 0, 0)
    second_parent.position = (-5, 0, 0)
    second_parent.rotation = (0, 45, 0)
    second_parent.scale = (2, 2, 2)
    child.position = (2, 0, 0)
    child.parent = first_parent
    original_world = child.world_position
    original_rotation = child.world_quaternion
    original_scale = child.world_scale

    child.set_parent(second_parent, keep_world=True)
    assert child.world_position.almost_equal(original_world)
    assert child.world_quaternion.almost_equal(original_rotation)
    assert child.world_scale.almost_equal(original_scale)
    assert not child.position.almost_equal(Vec3(2, 0, 0))

    second_parent.destroy()
    assert child.parent is None
    assert child.world_position.almost_equal(original_world)
    assert child.world_quaternion.almost_equal(original_rotation)
    assert child.world_scale.almost_equal(original_scale)


def test_cross_scene_parent_is_rejected() -> None:
    first = Scene("first").create_entity()
    second = Scene("second").create_entity()
    with pytest.raises(ValueError, match="different scene"):
        first.parent = second
