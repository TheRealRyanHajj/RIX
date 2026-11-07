from __future__ import annotations

import math
from pathlib import Path

import pytest

from rix import (
    CharacterController,
    Collider,
    Cube,
    DebugOverlay,
    Enemy,
    Entity,
    Game,
    Light,
    Model,
    PhysicsError,
    Plane,
    Player,
    Rigidbody,
    Scene,
    Sphere,
    Vec3,
)


def step(scene: Scene, seconds: float, count: int = 1) -> None:
    for _ in range(count):
        scene._native.step_physics(seconds)


def test_plain_motion_is_live_and_uses_semi_implicit_euler() -> None:
    scene = Scene("plain motion")
    entity = Entity(
        scene=scene,
        velocity=(1, 0, 0),
        acceleration=(2, 0, 0),
        angular_velocity=(0, 10, 0),
        angular_acceleration=(0, 20, 0),
    )

    entity.velocity.y = 3
    assert entity.velocity == Vec3(1, 3, 0)
    entity.velocity.y = 0
    step(scene, 0.5)

    assert entity.velocity.almost_equal(Vec3(2, 0, 0))
    assert entity.position.almost_equal(Vec3(1, 0, 0))
    assert entity.angular_velocity.almost_equal(Vec3(0, 20, 0))
    assert entity.forward.almost_equal(
        Vec3(-math.sin(math.radians(10)), 0, -math.cos(math.radians(10))),
        tolerance=1.0e-5,
    )


def test_parented_motion_remains_world_space() -> None:
    scene = Scene("parented motion")
    parent = Entity(scene=scene)
    parent.position = (10, 0, 0)
    parent.rotation = (0, 90, 0)
    parent.scale = (2, 2, 2)
    child = Entity(scene=scene, parent=parent, velocity=(1, 0, 0))

    before = child.world_position
    step(scene, 0.25)

    assert child.world_position.almost_equal(before + Vec3(0.25, 0, 0), tolerance=1e-5)


def test_speed_directions_facing_and_launch() -> None:
    scene = Scene("direction helpers")
    entity = Entity(scene=scene)
    entity.rotation = (0, 90, 0)

    assert entity.forward.almost_equal(Vec3(-1, 0, 0), tolerance=1e-5)
    assert entity.right.almost_equal(Vec3(0, 0, -1), tolerance=1e-5)
    assert entity.up.almost_equal(Vec3(0, 1, 0), tolerance=1e-5)
    assert entity.local_to_world_direction((0, 0, -1)).almost_equal(entity.forward)
    assert entity.world_to_local_direction(entity.forward).almost_equal(Vec3(0, 0, -1))

    entity.speed = 5
    assert entity.velocity.almost_equal(Vec3(-5, 0, 0), tolerance=1e-5)
    assert entity.movement_direction.almost_equal(entity.forward)
    entity.speed = 2
    assert entity.speed == pytest.approx(2)

    entity.launch((0, 3, 4), 10, face=True)
    assert entity.velocity.almost_equal(Vec3(0, 6, 8))
    assert entity.forward.almost_equal(Vec3(0, 0.6, 0.8), tolerance=1e-5)

    with pytest.raises(ValueError, match="zero length"):
        entity.face_direction((0, 0, 0))
    with pytest.raises(ValueError, match="zero length"):
        entity.launch((0, 0, 0), 1)
    for invalid in (-1, math.inf, math.nan):
        with pytest.raises(ValueError, match="finite and non-negative"):
            entity.speed = invalid


def test_motion_constructor_support_and_slot_reuse(tmp_path: Path) -> None:
    scene = Scene("constructors")
    model_path = tmp_path / "triangle.obj"
    model_path.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
        encoding="utf-8",
    )
    factories = (
        lambda: Entity(scene=scene, velocity=(1, 2, 3)),
        lambda: Cube(scene=scene, collider=False, velocity=(1, 2, 3)),
        lambda: Plane(scene=scene, collider=False, velocity=(1, 2, 3)),
        lambda: Sphere(scene=scene, collider=False, velocity=(1, 2, 3)),
        lambda: Light("point", scene=scene, velocity=(1, 2, 3)),
        lambda: Model(model_path, scene=scene, collider=False, velocity=(1, 2, 3)),
        lambda: Player(scene=scene, controls=False, velocity=(1, 2, 3)),
        lambda: Enemy(scene=scene, behavior="idle", velocity=(1, 2, 3)),
    )
    entities = [factory() for factory in factories]
    assert all(entity.velocity == Vec3(1, 2, 3) for entity in entities)

    old_index = entities[0]._handle.index
    entities[0].destroy()
    replacement = Entity(scene=scene)
    assert replacement._handle.index == old_index
    assert replacement.velocity == Vec3()
    assert replacement.acceleration == Vec3()
    assert replacement.angular_velocity == Vec3()
    assert replacement.angular_acceleration == Vec3()

    game = Game("overlay constructor")
    overlay = DebugOverlay(game, velocity=(1, 2, 3))
    assert overlay.velocity == Vec3(1, 2, 3)


def test_disabled_plain_entity_freezes_and_resumes() -> None:
    scene = Scene("disabled motion")
    entity = Entity(scene=scene, velocity=(2, 0, 0), acceleration=(1, 0, 0))
    entity.enabled = False
    step(scene, 0.5, 3)
    assert entity.position == Vec3()
    assert entity.velocity == Vec3(2, 0, 0)

    entity.enabled = True
    step(scene, 0.5)
    assert entity.velocity.almost_equal(Vec3(2.5, 0, 0))
    assert entity.position.almost_equal(Vec3(1.25, 0, 0))


def test_rigidbody_delegation_transfer_and_teleport_motion_policy() -> None:
    scene = Scene("rigid motion")
    entity = Cube(
        scene=scene,
        physics=True,
        gravity=False,
        velocity=(3, 0, 0),
        acceleration=(2, 0, 0),
        angular_velocity=(0, 90, 0),
    )
    body = entity.get_component(Rigidbody)
    assert body is not None

    assert body.linear_velocity.almost_equal(Vec3(3, 0, 0))
    assert body.angular_velocity.almost_equal(Vec3(0, 90, 0))
    step(scene, 0.25)
    assert entity.velocity.x > 3
    assert entity.position.x > 0.7

    before = Vec3(entity.velocity)
    entity.teleport((5, 6, 7), rotation=(0, 45, 0))
    assert entity.velocity.almost_equal(before)
    entity.teleport((1, 2, 3), reset_motion=True)
    assert entity.velocity == Vec3()
    assert entity.acceleration == Vec3()
    assert entity.angular_velocity == Vec3()

    entity.velocity = (4, 0, 0)
    body.remove()
    entity.get_component(Collider).remove()  # type: ignore[union-attr]
    step(scene, 0.25)
    assert entity.position.x > 1.9


def test_kinematic_and_character_motion_delegate_on_the_fixed_clock() -> None:
    scene = Scene("delegated motion")
    kinematic = Cube(
        scene=scene,
        physics=True,
        kinematic=True,
        gravity=False,
        velocity=(2, 0, 0),
        angular_velocity=(0, 40, 0),
    )
    step(scene, 0.25)
    assert kinematic.position.x == pytest.approx(0.5, abs=1e-4)
    assert kinematic.rotation.y == pytest.approx(10, abs=0.2)

    kinematic.enabled = False
    frozen = Vec3(kinematic.position)
    step(scene, 0.5)
    assert kinematic.position.almost_equal(frozen)
    assert kinematic.velocity.almost_equal(Vec3(2, 0, 0))
    kinematic.enabled = True
    step(scene, 0.25)
    assert kinematic.position.x == pytest.approx(1.0, abs=1e-4)

    character_scene = Scene("character acceleration")
    player = Player(
        scene=character_scene, controls=False, acceleration=(2, 0, 0)
    )
    step(character_scene, 0.5)
    assert player.velocity.x == pytest.approx(1, abs=1e-4)
    assert player.position.x == pytest.approx(0.5, abs=1e-4)
    player.teleport((4, 5, 6))
    assert player.velocity.x == pytest.approx(1, abs=1e-4)
    player.teleport((0, 0, 0), reset_motion=True)
    assert player.velocity == Vec3()
    assert player.acceleration == Vec3()


def test_collider_only_motion_is_rejected() -> None:
    scene = Scene("static collider")
    with pytest.raises(ValueError, match="kinematic Rigidbody"):
        Cube(scene=scene, collider=True, velocity=(1, 0, 0))

    entity = Cube(scene=scene, collider=True)
    with pytest.raises(PhysicsError, match="kinematic Rigidbody"):
        entity.velocity = (1, 0, 0)

    manual = Entity(scene=scene, velocity=(1, 0, 0))
    with pytest.raises(PhysicsError, match="kinematic Rigidbody"):
        manual.add_component(Collider)


def test_character_velocity_yaw_and_player_view_vectors() -> None:
    scene = Scene("character motion")
    player = Player(
        scene=scene,
        controls=False,
        velocity=(1, 0, 0),
        angular_velocity=(0, 90, 0),
    )
    controller = player.get_component(CharacterController)
    assert controller is not None
    controller.linear_velocity = (2, 0, 0)
    assert player.velocity.almost_equal(Vec3(2, 0, 0))

    view_before = player.view_forward
    step(scene, 0.5)
    assert player.view_forward.x < view_before.x - 0.5
    assert player.view_right.length == pytest.approx(1)
    assert player.view_up.length == pytest.approx(1)
    with pytest.raises(PhysicsError, match="upright"):
        player.angular_velocity = (1, 0, 0)
    with pytest.raises(PhysicsError, match="upright"):
        player.angular_acceleration = (0, 0, 1)


def test_player_tuning_keyword_migration_is_intentionally_breaking() -> None:
    scene = Scene("migration")
    player = Player(scene=scene, controls=False, move_speed=7, move_acceleration=12)
    assert player.controller.speed == pytest.approx(7)
    assert player.controller.acceleration == pytest.approx(12)

    with pytest.raises(TypeError, match="renamed to move_speed"):
        Player(scene=scene, controls=False, speed=7)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="move_acceleration"):
        Player(scene=scene, controls=False, acceleration=12)  # type: ignore[arg-type]


def test_nonfinite_motion_is_rejected() -> None:
    scene = Scene("validation")
    entity = Entity(scene=scene)
    for attribute in (
        "velocity",
        "acceleration",
        "angular_velocity",
        "angular_acceleration",
    ):
        with pytest.raises(ValueError, match="finite"):
            setattr(entity, attribute, (math.nan, 0, 0))
