from __future__ import annotations

from dataclasses import dataclass

import pytest

import rix.advanced as advanced
import rix.time as easy_time

from rix import (
    Button,
    Collider,
    Column,
    Cube,
    Game,
    Light,
    Panel,
    Plane,
    Player,
    Rigidbody,
    Row,
    Sphere,
    Text,
)


def test_game_owns_visible_default_world_camera_and_lights() -> None:
    game = Game("beginner")
    assert game.scene is not None
    cube = Cube(color="red")
    assert cube.scene is game.scene
    assert cube.get_component(Collider) is not None
    assert game.camera is game.scene.camera
    game.camera.position = (0, 5, 10)
    game.camera.look_at((0, 0, 0))
    assert tuple(game.scene._native.camera_info()[0]) == pytest.approx((0, 5, 10))
    assert game.lighting.ambient == pytest.approx(0.16)
    assert game.lighting.directional == pytest.approx(0.95)

    directionals = game.scene.lights("directional")
    assert [light.name for light in directionals] == [
        "Directional Key Light",
        "Directional Fill Light",
    ]
    assert directionals[0].shadow_bias == pytest.approx(0.0005)
    key_to_light = tuple(-value for value in directionals[0].forward)
    fill_to_light = tuple(-value for value in directionals[1].forward)
    assert all(value > 0 for value in key_to_light)
    assert len({round(value, 3) for value in key_to_light}) == 3
    assert fill_to_light[0] < 0 < fill_to_light[1]
    assert fill_to_light[2] < 0

    game.lighting.directional = 0.475
    assert directionals[0].intensity == pytest.approx(0.475)
    assert directionals[1].intensity == pytest.approx(0.275)

    default_ambient = next(
        entity for entity in game.scene.entities if entity.name == "Ambient Light"
    )
    custom = Light("ambient", intensity=0.5)
    assert not default_ambient.is_alive
    assert custom.scene is game.scene
    assert game.lighting.ambient == pytest.approx(0.5)
    custom_sun = Light("directional", intensity=1.1)
    assert all(not light.is_alive for light in directionals)
    assert game.scene.lights("directional") == (custom_sun,)
    assert game.lighting.directional == pytest.approx(1.1)
    game.close()
    assert game.scene is None


def test_curated_time_and_advanced_modules_keep_compatibility_types() -> None:
    assert easy_time.Timer is __import__("rix", fromlist=["Timer"]).Timer
    assert advanced.Rigidbody is Rigidbody


def test_multiple_games_have_deterministic_implicit_ownership() -> None:
    first = Game("first")
    first_cube = Cube()
    second = Game("second")
    second_cube = Cube()
    assert first_cube.scene is first.scene
    assert second_cube.scene is second.scene
    with first:
        contextual = Cube()
        assert contextual.scene is first.scene
    assert first.scene is None
    assert second.scene is not None
    restored = Cube()
    assert restored.scene is second.scene
    second.close()


@dataclass
class _Pointer:
    delta: tuple[float, float] = (8.0, -4.0)


class _PlayerInput:
    pointer = _Pointer()
    pointer_locked = True
    pointer_lock_requested = True

    def value(self, action: str) -> float:
        return 1.0 if action == "player_forward" else 0.0

    def down(self, action: str) -> bool:
        return action == "player_sprint"

    def pressed(self, _action: str) -> bool:
        return False

    def gamepad_axis(self, _axis: str) -> float:
        return 0.0


class _CallbackInput:
    def pressed(self, action: str) -> bool:
        return action in ("interact", "test_action", "key_tab", "mouse_left")


def test_transform_color_and_physics_shortcuts_use_native_components() -> None:
    game = Game()
    cube = Cube(
        x=1,
        y=3,
        z=-2,
        ry=45,
        scale=2,
        color="#FF5733",
        physics=True,
        mass=5,
    )
    assert tuple(cube.position) == pytest.approx((1, 3, -2))
    assert cube.ry == pytest.approx(45)
    assert tuple(cube.scale) == pytest.approx((2, 2, 2))
    assert cube.get_component(Collider) is not None
    body = cube.get_component(Rigidbody)
    assert body is not None and body.mass == pytest.approx(5)
    assert cube.get_component(Collider).layer == "dynamic"  # type: ignore[union-attr]

    static = Cube(collider=True, friction=0.8, bounciness=0.25)
    static_collider = static.get_component(Collider)
    assert static_collider is not None and static_collider.layer == "static"
    assert static_collider.material.friction == pytest.approx(0.8)
    assert static_collider.material.restitution == pytest.approx(0.25)
    fast = Sphere(
        physics=True,
        gravity=False,
        continuous=True,
        friction=0.1,
        bounciness=0.7,
    )
    fast_body = fast.get_component(Rigidbody)
    assert fast_body is not None and not fast_body.use_gravity and fast_body.continuous
    kinematic = Cube(physics=True, kinematic=True)
    assert kinematic.get_component(Rigidbody).body_type == "kinematic"  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="position"):
        Cube(position=(0, 0, 0), x=1)
    with pytest.raises(ValueError, match="mass"):
        Cube(mass=2)
    with pytest.raises(ValueError, match="trigger"):
        Cube(physics=True, trigger=True)
    with pytest.raises(ValueError, match="gravity"):
        Cube(gravity=False)
    with pytest.raises(ValueError, match="continuous"):
        Cube(physics=True, continuous=True, kinematic=True)
    with pytest.raises(ValueError, match="sensor"):
        Cube(trigger=True, collision_layer="dynamic")
    with pytest.raises(ValueError, match="color"):
        Cube(color="not-a-color")
    game.close()


def test_parent_constructor_and_entity_helpers_use_native_ownership() -> None:
    game = Game()
    parent = Cube(x=2, ry=20)
    child = Cube(parent=parent, position=(0, 1, 0), scale=0.5, collider=False)
    assert child.parent == parent
    assert tuple(child.world_position) == pytest.approx((2, 1, 0))
    parent.move((1, 0, -2)).rotate((0, 25, 0))
    parent.move(1, 0, 0).rotate(0, 5, 0)
    assert tuple(child.world_position) == pytest.approx((4, 1, -2))
    assert child.distance_to(parent) == pytest.approx(1)
    child.look_at((4, 1, -8))
    assert child.world_quaternion.rotate((0, 0, -1)).z < -0.99
    assert child.hide() is child and not child.visible
    assert child.show() is child and child.visible
    assert child.disable() is child and not child.enabled
    assert child.enable() is child and child.enabled

    plane = Plane(x=4, y=-1, rz=10, size=3)
    assert tuple(plane.position) == pytest.approx((4, -1, 0))
    assert plane.rz == pytest.approx(10)

    dynamic = Sphere(y=4, physics=True)
    dynamic.teleport((5, 6, 7), (0, 30, 0))
    assert tuple(dynamic.position) == pytest.approx((5, 6, 7))
    player = Player(position=(0, 1, 0), controls=False)
    player.teleport((1, 2, 3), (0, 90, 0))
    assert tuple(player.position) == pytest.approx((1, 2, 3))

    other = Game()
    with pytest.raises(ValueError, match="parent and scene"):
        Cube(parent=parent, scene=other.scene)
    other.close()
    game.close()


def test_player_axis_shortcuts_and_scene_free_raycast_helpers() -> None:
    game = Game()
    player = Player(y=1, controls=False)
    target = Cube(z=-4, y=2, collider=True)
    assert tuple(player.position) == pytest.approx((0, 1, 0))
    hit = player.raycast(10)
    assert hit is not None and hit.entity == target
    game_hit = game.raycast(
        (0, 2, 0), (0, 0, -1), distance=10, exclude=player
    )
    assert game_hit is not None and game_hit.entity == target
    with pytest.raises(ValueError, match="position"):
        Player(position=(0, 1, 0), y=1)
    game.close()


def test_default_player_and_direct_ui_factories_require_no_subclass() -> None:
    game = Game()
    player = Player(position=(0, 1, 0))
    game._scheduler.begin_run()
    game._callback_active = True
    game._gameplay_thread_id = __import__("threading").get_ident()
    try:
        game._scheduler.advance(game.scene, 1.0 / 60.0)
    finally:
        game._callback_active = False
        game._gameplay_thread_id = None
    assert player.controller.mode == "first_person"
    assert game.input.bindings("player_jump")[0].control == "key:space"
    assert game.input.pointer_lock_requested

    title = Text("Health: 100", x=20, y=20)
    panel = Panel(x=10, y=10, width=240, height=80)
    clicked: list[bool] = []
    button = Button("Quit", click=lambda: clicked.append(True))
    assert title in game.scene.hud.elements
    assert panel in game.scene.hud.elements
    assert Row(title, button).direction == "horizontal"
    assert Column(title, button).direction == "vertical"
    game.scene.hud._advance((640, 360), True, (1280, 720))
    assert clicked == [True]
    game.close()


def test_default_player_moves_and_mouse_look_updates_persistent_camera() -> None:
    game = Game()
    Cube(y=-0.5, scale=(20, 1, 20), collider=True)
    player = Player(position=(0, 1, 0))
    player._controls_bound = True
    game._input = _PlayerInput()  # type: ignore[assignment]
    initial_forward = tuple(game.camera.forward)
    game._scheduler.begin_run()
    for _ in range(20):
        game._scheduler.advance(game.scene, 1.0 / 60.0)
    assert player.position.z < -0.1
    assert player.controller.sprinting
    assert tuple(game.camera.forward) != pytest.approx(initial_forward)
    assert tuple(game.camera.position) == pytest.approx(
        (player.position.x, player.position.y + 1.55, player.position.z)
    )
    game.close()


def test_function_callbacks_and_timers_run_on_scheduler() -> None:
    game = Game()
    updates: list[float] = []
    fixed: list[float] = []
    timers: list[str] = []
    game.on_update(updates.append)
    game.on_fixed_update(fixed.append)
    game.after(0.01, lambda: timers.append("once"))
    game.every(0.01, lambda: timers.append("repeat"))
    game._scheduler.begin_run()
    game._callback_active = True
    game._gameplay_thread_id = __import__("threading").get_ident()
    try:
        game._scheduler.advance(game.scene, 1.0 / 60.0)
    finally:
        game._callback_active = False
        game._gameplay_thread_id = None
    assert len(updates) == len(fixed) == 1
    assert timers == ["once", "repeat"]
    game.close()


def test_decorator_callbacks_subscription_and_timer_cancellation() -> None:
    game = Game()
    calls: list[str] = []

    @game.update
    def render_update(_dt: float) -> None:
        calls.append("update")

    @game.fixed_update
    def simulation_update(_dt: float) -> None:
        calls.append("fixed")

    @game.on_key("tab")
    def tab_pressed() -> None:
        calls.append("tab")

    @game.on_mouse("left")
    def mouse_pressed() -> None:
        calls.append("mouse")

    cancelled = game.subscribe_update(lambda _dt: calls.append("cancelled"))
    cancelled.cancel()
    cancelled_timer = game.after(0, lambda: calls.append("cancelled timer"))
    cancelled_timer.cancel()
    repeating = game.every(0.01, lambda: calls.append("repeat"))
    game.after(0, lambda: game.after(0, lambda: calls.append("nested")))
    assert game.input.bindings("key_tab")[0].control == "key:tab"
    assert game.input.bindings("mouse_left")[0].control == "mouse:left"
    game._input = _CallbackInput()  # type: ignore[assignment]
    game._scheduler.begin_run()
    game._scheduler.advance(game.scene, 1 / 60)
    repeating.cancel()
    game._scheduler.advance(game.scene, 1 / 60)

    assert calls.count("update") == 2
    assert calls.count("fixed") == 2
    assert calls.count("tab") == 2
    assert calls.count("mouse") == 2
    assert calls.count("repeat") == 1
    assert calls.count("nested") == 1
    assert "cancelled" not in calls and "cancelled timer" not in calls
    game.close()


def test_input_callback_is_not_lost_on_a_frame_without_a_fixed_tick() -> None:
    game = Game()
    calls: list[str] = []
    game.input.bind("interact", "key:e")
    game.on_input("interact", lambda: calls.append("interact"))
    game._input = _CallbackInput()  # type: ignore[assignment]
    game._scheduler.begin_run()

    game._scheduler.advance(game.scene, 1 / 120)

    assert game.scheduler_stats.fixed_ticks == 0
    assert calls == ["interact"]
    game.close()


def test_regular_function_input_collision_and_trigger_phases() -> None:
    game = Game()
    pressed: list[str] = []
    game.input.bind("test_action", "key:tab")
    game.on_input("test_action", lambda: pressed.append("input"))
    game._input = _CallbackInput()  # type: ignore[assignment]

    floor = Cube(y=-0.5, scale=(5, 1, 5), collider=True, name="Floor")
    ball = Sphere(y=0.7, physics=True, name="Ball")
    collision_phases: list[str] = []
    game.on_collision(ball, lambda _event: collision_phases.append("enter"))
    game.on_collision(
        ball, lambda _event: collision_phases.append("exit"), phase="exit"
    )
    trigger = Cube(x=4, scale=2, trigger=True, name="Trigger")
    probe = Sphere(x=4, physics=True, name="Probe")
    trigger_phases: list[str] = []
    game.on_collision(
        probe,
        lambda _event: trigger_phases.append("enter"),
        trigger=True,
    )
    game.on_collision(
        probe,
        lambda _event: trigger_phases.append("exit"),
        phase="exit",
        trigger=True,
    )

    game._scheduler.begin_run()
    for _ in range(30):
        game._scheduler.advance(game.scene, 1.0 / 60.0)
    assert pressed
    assert "enter" in collision_phases
    assert "enter" in trigger_phases

    ball.get_component(Rigidbody).teleport((0, 5, 0))  # type: ignore[union-attr]
    probe.get_component(Rigidbody).teleport((8, 5, 0))  # type: ignore[union-attr]
    game._scheduler.advance(game.scene, 1.0 / 60.0)
    assert collision_phases[-1] == "exit"
    assert trigger_phases[-1] == "exit"
    assert floor.is_alive and trigger.is_alive
    game.close()


def test_trigger_entity_decorators_receive_other_entity() -> None:
    game = Game()
    trigger = Cube(scale=2, trigger=True)
    probe = Sphere(physics=True)
    phases: list[tuple[str, Entity]] = []

    @trigger.on_enter
    def entered(other: Entity) -> None:
        phases.append(("enter", other))

    @trigger.on_exit
    def exited(other: Entity) -> None:
        phases.append(("exit", other))

    game._scheduler.begin_run()
    game._scheduler.advance(game.scene, 1 / 60)
    probe.teleport((5, 5, 0))
    game._scheduler.advance(game.scene, 1 / 60)
    assert phases == [("enter", probe), ("exit", probe)]
    game.close()


def test_trigger_callback_shortcut_dispatches_existing_physics_event() -> None:
    game = Game()
    entered: list[str] = []
    Cube(scale=3, trigger=lambda event: entered.append(event.other.name), name="Zone")
    Cube(y=0.5, physics=True, name="Falling cube")
    game._scheduler.begin_run()
    game._callback_active = True
    game._gameplay_thread_id = __import__("threading").get_ident()
    try:
        for _ in range(5):
            game._scheduler.advance(game.scene, 1.0 / 60.0)
    finally:
        game._callback_active = False
        game._gameplay_thread_id = None
    assert "Falling cube" in entered
    game.close()


