from __future__ import annotations

import pytest

from rix import (
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


class _JumpInput:
    def __init__(self) -> None:
        self.jump_pressed = True
        self.pointer_lock_requested = False
        self.pointer_locked = False
        self.pointer = type("Pointer", (), {"delta": (0.0, 0.0)})()

    def bind(self, *_args: object, **_kwargs: object) -> None:
        pass

    def pressed(self, action: str) -> bool:
        if action == "player_jump" and self.jump_pressed:
            self.jump_pressed = False
            return True
        return False

    def down(self, _action: str) -> bool:
        return False

    def value(self, _action: str) -> float:
        return 0.0

    def gamepad_axis(self, _axis: str) -> float:
        return 0.0


class _HeldJumpInput(_JumpInput):
    def __init__(self) -> None:
        super().__init__()
        self.jump_pressed = False

    def down(self, action: str) -> bool:
        return action == "player_jump"


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
        move_speed=3.0,
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
        air_acceleration=7.0,
        ground_friction=5.0,
        stop_speed=1.25,
        air_speed_cap=1.75,
        horizontal_speed_limit=12.0,
        jump_speed=6.5,
        max_slope_degrees=42.0,
        step_height=0.35,
        sprint_multiplier=1.75,
        crouch_height=1.2,
        crouch_speed_multiplier=0.4,
    )
    assert controller.radius == pytest.approx(0.45)
    assert controller.height == pytest.approx(1.9)
    assert controller.speed == pytest.approx(6.0)
    assert controller.air_acceleration == pytest.approx(7.0)
    assert controller.ground_friction == pytest.approx(5.0)
    assert controller.stop_speed == pytest.approx(1.25)
    assert controller.air_speed_cap == pytest.approx(1.75)
    assert controller.horizontal_speed_limit == pytest.approx(12.0)
    assert controller.max_slope_degrees == pytest.approx(42.0)
    assert controller.step_height == pytest.approx(0.35)
    assert controller.sprint_multiplier == pytest.approx(1.75)
    assert controller.crouch_height == pytest.approx(1.2)
    assert controller.crouch_speed_multiplier == pytest.approx(0.4)
    with pytest.raises(ValueError, match="cannot also have collider"):
        entity.add_component(Collider)

    collider_entity = Entity(scene=scene)
    collider_entity.add_component(Collider)
    with pytest.raises(ValueError, match="cannot also have collider"):
        collider_entity.add_component(CharacterController)

    for kwargs, message in (
        ({"mode": "vehicle"}, "mode"),
        ({"radius": 0.5, "height": 1.0}, "diameter"),
        ({"air_acceleration": -0.1}, "air_acceleration"),
        ({"ground_friction": -0.1}, "ground_friction"),
        ({"stop_speed": -0.1}, "stop_speed"),
        ({"air_speed_cap": -0.1}, "air_speed_cap"),
        ({"horizontal_speed_limit": -0.1}, "horizontal_speed_limit"),
        ({"max_slope_degrees": 90.0}, "max_slope"),
        ({"step_height": -1.0}, "step_height"),
        ({"sprint_multiplier": 0.9}, "sprint_multiplier"),
        ({"crouch_height": 0.8}, "crouch_height"),
        ({"crouch_speed_multiplier": 1.1}, "crouch_speed_multiplier"),
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


def test_sprint_crouch_and_unbuffered_jump_use_native_motor_state() -> None:
    scene = Scene("locomotion")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(40.0, 1.0, 40.0),
        collider=True,
        scene=scene,
    )
    player = Player(
        position=(0.0, 0.0, 0.0),
        move_speed=3.0,
        move_acceleration=60.0,
        sprint_multiplier=1.75,
        crouch_height=1.2,
        crouch_speed_multiplier=0.4,
        scene=scene,
    )
    _step(scene, 5)

    player.move((1.0, 0.0, 0.0), sprint=True)
    _step(scene, 30)
    assert player.controller.sprinting
    assert not player.controller.crouched
    assert player.controller.linear_velocity.x == pytest.approx(5.25, abs=0.1)

    player.move((1.0, 0.0, 0.0), sprint=True, crouch=True)
    _step(scene, 30)
    assert player.controller.crouched
    assert not player.controller.sprinting
    assert player.controller.linear_velocity.x == pytest.approx(1.2, abs=0.15)

    player.move((0.0, 0.0, 0.0))
    _step(scene, 2)
    assert not player.controller.crouched

    unbuffered = Player(position=(0.0, 1.0, 5.0), jump_speed=5.0, scene=scene)
    unbuffered.move((0.0, 0.0, 0.0), jump=True)
    _step(scene, 120)
    assert unbuffered.controller.grounded
    assert -0.3 < unbuffered.controller.linear_velocity.y <= 0.0


def test_automatic_player_latches_jump_until_the_next_fixed_tick() -> None:
    from rix import Game

    game = Game("jump latch")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(20.0, 1.0, 20.0),
        collider=True,
    )
    player = Player(position=(0.0, 0.0, 0.0))
    _step(game.scene, 5)
    assert player.controller.grounded

    game._input = _JumpInput()  # type: ignore[assignment]
    player._controls_bound = True
    player.update(1.0 / 120.0)
    assert player._jump_requested

    player.fixed_update(1.0 / 60.0)
    assert not player._jump_requested
    game.scene._native.step_physics(1.0 / 60.0)
    assert player.controller.linear_velocity.y > 0.0
    game.close()


def test_automatic_player_does_not_turn_held_jump_into_auto_hop() -> None:
    from rix import Game

    game = Game("held jump")
    player = Player(position=(0.0, 0.0, 0.0))
    game._input = _HeldJumpInput()  # type: ignore[assignment]
    player._controls_bound = True

    player.update(1.0 / 60.0)

    assert not player._jump_requested
    game.close()


def test_timed_bunny_hop_skips_landing_friction_and_keeps_momentum() -> None:
    scene = Scene("bunny hop")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(40.0, 1.0, 40.0),
        collider=True,
        scene=scene,
    )
    player = Player(
        position=(0.0, 0.0, 0.0),
        move_speed=4.0,
        move_acceleration=60.0,
        controls=False,
        scene=scene,
    )
    _step(scene, 5)
    player.move((1.0, 0.0, 0.0))
    _step(scene, 20)
    incoming_speed = player.controller.linear_velocity.x
    assert incoming_speed > 3.9

    player.move((0.0, 0.0, 0.0), jump=True)
    _step(scene, 1)
    began_falling = False
    landing_speed = None
    second_takeoff_speed = None
    for _ in range(180):
        velocity = player.controller.linear_velocity
        began_falling = began_falling or velocity.y < -0.5
        if began_falling and player.controller.grounded:
            landing_speed = velocity.x
            player.move((0.0, 0.0, 0.0), jump=True)
        else:
            player.move((0.0, 0.0, 0.0))
        _step(scene, 1)
        velocity = player.controller.linear_velocity
        if landing_speed is not None and velocity.y > 3.0:
            second_takeoff_speed = velocity.x
            break

    assert landing_speed is not None
    assert second_takeoff_speed is not None
    assert second_takeoff_speed > incoming_speed * 0.95


def test_wish_direction_is_normalized_and_air_acceleration_is_projected() -> None:
    scene = Scene("air movement")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(40.0, 1.0, 40.0),
        collider=True,
        scene=scene,
    )
    player = Player(
        move_speed=3.0,
        move_acceleration=30.0,
        air_acceleration=8.0,
        air_speed_cap=1.5,
        controls=False,
        scene=scene,
    )
    _step(scene, 5)
    player.move((1.0, 0.0, 1.0))
    _step(scene, 20)
    velocity = player.controller.linear_velocity
    assert Vec3(velocity.x, 0.0, velocity.z).length == pytest.approx(3.0, abs=0.1)

    player.controller.linear_velocity = (3.0, 2.0, 0.0)
    player.move((1.0, 0.0, 0.0))
    _step(scene, 1)
    assert player.controller.linear_velocity.x == pytest.approx(3.0, abs=0.02)

    player.controller.linear_velocity = (3.0, 2.0, 0.0)
    player.move((0.0, 0.0, 1.0))
    _step(scene, 1)
    strafed = player.controller.linear_velocity
    assert strafed.z < -0.1
    assert Vec3(strafed.x, 0.0, strafed.z).length > 3.0
