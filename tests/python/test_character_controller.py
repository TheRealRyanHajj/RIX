from __future__ import annotations

import pytest

from easy3d import (
    CharacterController,
    Collider,
    Cube,
    Entity,
    PhysicsError,
    Player,
    Scene,
    Vec3,
    physics,
)


def _step(scene: Scene, count: int) -> None:
    for _ in range(count):
        scene._native.step_physics(1.0 / 60.0)


def test_first_person_motor_steps_jumps_lands_and_syncs_transform() -> None:
    scene = Scene("character course")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(30.0, 1.0, 30.0),
        collider=True,
        scene=scene,
    )
    Cube(
        position=(0.0, 0.15, -2.0),
        size=(2.0, 0.3, 1.0),
        collider=True,
        scene=scene,
    )
    player = Player(
        position=(0.0, 0.0, 0.0),
        controller="first_person",
        speed=3.0,
        scene=scene,
    )

    _step(scene, 5)
    assert player.controller.grounded
    hit = physics.raycast(
        scene,
        (0.0, 3.0, 0.0),
        (0.0, -1.0, 0.0),
        5.0,
        layers=("character",),
    )
    assert hit is not None and hit.entity == player
    player.move((0.0, 0.0, 1.0))
    _step(scene, 120)
    assert player.position.z < -4.0
    assert player.position.y == pytest.approx(0.0, abs=0.05)
    assert player.controller.grounded

    player.move((0.0, 0.0, 0.0), jump=True)
    _step(scene, 10)
    assert not player.controller.grounded
    assert player.position.y > 0.3
    assert player.controller.linear_velocity.y > 0.0
    _step(scene, 120)
    assert player.controller.grounded
    assert player.controller.ground_normal.almost_equal(Vec3(0.0, 1.0, 0.0), 0.01)


def test_third_person_facing_teleport_and_component_lifetime() -> None:
    scene = Scene()
    Cube(position=(0.0, -0.5, 0.0), size=(20.0, 1.0, 20.0), collider=True, scene=scene)
    player = Player(
        position=(0.0, 0.0, 0.0), controller="third_person", scene=scene
    )
    controller = player.controller
    assert player.has_component(CharacterController)
    assert controller.mode == "third_person"
    controller.set_input((1.0, 0.0, 0.0), heading_degrees=0.0)
    _step(scene, 30)
    assert player.position.x > 1.0
    assert abs(player.quaternion.y) > 0.5

    controller.teleport((2.0, 1.0, 3.0), heading_degrees=90.0)
    assert player.position.almost_equal(Vec3(2.0, 1.0, 3.0), 1.0e-4)
    with pytest.raises(PhysicsError, match="physics-owned"):
        player.position = (0.0, 0.0, 0.0)
    with pytest.raises(PhysicsError, match="cannot be parented"):
        player.parent = Entity(scene=scene)

    player.remove_component(CharacterController)
    assert not player.has_component(CharacterController)
    player.position = (0.0, 0.0, 0.0)


def test_character_configuration_and_component_exclusivity_validation() -> None:
    scene = Scene()
    entity = Entity(scene=scene)
    controller = entity.add_component(
        CharacterController,
        radius=0.45,
        height=1.9,
        speed=6.0,
        acceleration=24.0,
        air_control=0.4,
        jump_speed=6.5,
        max_slope_degrees=42.0,
        step_height=0.35,
    )
    assert controller.radius == pytest.approx(0.45)
    assert controller.height == pytest.approx(1.9)
    assert controller.speed == pytest.approx(6.0)
    assert controller.max_slope_degrees == pytest.approx(42.0)
    assert controller.step_height == pytest.approx(0.35)
    with pytest.raises(ValueError, match="cannot also have collider"):
        entity.add_component(Collider)

    collider_entity = Entity(scene=scene)
    collider_entity.add_component(Collider)
    with pytest.raises(ValueError, match="cannot also have collider"):
        collider_entity.add_component(CharacterController)

    for kwargs, message in (
        ({"mode": "vehicle"}, "mode"),
        ({"radius": 0.5, "height": 1.0}, "diameter"),
        ({"air_control": 1.1}, "air_control"),
        ({"max_slope_degrees": 90.0}, "max_slope"),
        ({"step_height": -1.0}, "step_height"),
    ):
        candidate = Entity(scene=scene)
        with pytest.raises(ValueError, match=message):
            candidate.add_component(CharacterController, **kwargs)

    count_before = scene.entity_count
    with pytest.raises(ValueError, match="mode"):
        Player(controller="vehicle", scene=scene)  # type: ignore[arg-type]
    assert scene.entity_count == count_before


def test_character_destroy_and_scene_clear_release_native_state() -> None:
    scene = Scene()
    first = Player(scene=scene)
    second = Player(position=(2.0, 0.0, 0.0), scene=scene)
    first.destroy()
    _step(scene, 1)
    assert second.is_alive
    scene.clear()
    assert scene.entity_count == 0
