"""Convenience player entity backed by the native character motor."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import TYPE_CHECKING

from .components import CharacterController, CharacterMode
from .entity import Entity
from .math import Quat, Vec3

_UNSET = object()

if TYPE_CHECKING:
    from .components import CollisionLayer
    from .gameplay import HitscanWeapon
    from .physics import PhysicsHit
    from .scene import Scene
    from .world import World


class Player(Entity):
    """An entity with a configured first- or third-person character controller."""

    if TYPE_CHECKING:
        weapon: HitscanWeapon

    def __init__(
        self,
        world: World | None = None,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        controller: CharacterMode = "first_person",
        radius: float = 0.4,
        height: float = 1.8,
        move_speed: float = 5.0,
        move_acceleration: float = 30.0,
        air_acceleration: float = 8.0,
        ground_friction: float = 6.0,
        stop_speed: float = 1.0,
        air_speed_cap: float = 1.5,
        horizontal_speed_limit: float | None = None,
        jump_speed: float = 5.0,
        max_slope_degrees: float = 50.0,
        step_height: float = 0.4,
        sprint_multiplier: float = 1.6,
        crouch_height: float | None = None,
        crouch_speed_multiplier: float = 0.5,
        controls: bool = True,
        mouse_sensitivity: float = 0.1,
        sprinting: bool = True,
        crouching: bool = True,
        camera_height: float = 1.55,
        third_person_distance: float = 5.0,
        name: str = "Player",
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        speed: object = _UNSET,
    ) -> None:
        if world is not None:
            from .world import World

            if not isinstance(world, World):
                raise TypeError("world must be a rix.World or None")
            if world.scene is None:
                raise RuntimeError("World has no active scene")
            if scene is not None and scene is not world.scene:
                raise ValueError("world and scene must refer to the same scene")
            scene = world.scene
        if speed is not _UNSET:
            raise TypeError(
                "Player(speed=...) was renamed to move_speed; use velocity for "
                "world-space entity motion"
            )
        if not isinstance(controls, bool):
            raise TypeError("controls must be a bool")
        if not isinstance(sprinting, bool) or not isinstance(crouching, bool):
            raise TypeError("sprinting and crouching must be bools")
        sensitivity = float(mouse_sensitivity)
        eye_height = float(camera_height)
        follow_distance = float(third_person_distance)
        if not math.isfinite(sensitivity) or sensitivity < 0:
            raise ValueError("mouse_sensitivity must be finite and non-negative")
        if not math.isfinite(eye_height) or eye_height <= 0:
            raise ValueError("camera_height must be finite and positive")
        if not math.isfinite(follow_distance) or follow_distance <= 0:
            raise ValueError("third_person_distance must be finite and positive")
        self._automatic_controls = controls
        self._controls_bound = False
        self._mouse_sensitivity = sensitivity
        self._sprint_enabled = sprinting
        self._crouch_enabled = crouching
        self._camera_height = eye_height
        self._third_person_distance = follow_distance
        self._yaw = 0.0
        self._pitch = -8.0 if controller == "first_person" else -18.0
        self._jump_requested = False
        if position is not None and any(value is not None for value in (x, y, z)):
            raise ValueError("position cannot be combined with x, y, or z")
        position_value = Vec3.from_value(
            position
            if position is not None
            else (
                0.0 if x is None else x,
                0.0 if y is None else y,
                0.0 if z is None else z,
            )
        )
        if isinstance(acceleration, (int, float)):
            raise TypeError(
                "Player(acceleration=...) was renamed to move_acceleration; "
                "entity acceleration must be a 3D vector"
            )
        super().__init__(
            name,
            scene=scene,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        try:
            self.position = position_value
            self.add_component(
                CharacterController,
                mode=controller,
                radius=radius,
                height=height,
                speed=move_speed,
                acceleration=move_acceleration,
                air_acceleration=air_acceleration,
                ground_friction=ground_friction,
                stop_speed=stop_speed,
                air_speed_cap=air_speed_cap,
                horizontal_speed_limit=horizontal_speed_limit,
                jump_speed=jump_speed,
                max_slope_degrees=max_slope_degrees,
                step_height=step_height,
                sprint_multiplier=sprint_multiplier,
                crouch_height=crouch_height,
                crouch_speed_multiplier=crouch_speed_multiplier,
            )
            self._sync_camera()
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise

    @property
    def controller(self) -> CharacterController:
        result = self.get_component(CharacterController)
        if result is None:
            raise RuntimeError("player character controller was removed")
        return result

    @property
    def controls_enabled(self) -> bool:
        return self._automatic_controls

    def _view_rotation(self) -> Quat:
        yaw_offset = self.scene._native.entity_character_yaw_offset(self._handle)
        return Quat.from_euler((self._pitch, self._yaw + yaw_offset, 0.0))

    @property
    def view_forward(self) -> Vec3:
        return self._view_rotation().rotate((0, 0, -1))

    @property
    def view_right(self) -> Vec3:
        return self._view_rotation().rotate((1, 0, 0))

    @property
    def view_up(self) -> Vec3:
        return self._view_rotation().rotate((0, 1, 0))

    def set_controls_enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("controls enabled state must be a bool")
        self._automatic_controls = value
        if value:
            self._bind_default_controls()
        else:
            self.move((0, 0, 0))

    def move(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
        sprint: bool = False,
        crouch: bool = False,
    ) -> None:
        """Set movement intent; ``jump=True`` requests only the next fixed tick."""

        self.controller.set_input(
            movement,
            heading_degrees=heading_degrees,
            jump=jump,
            sprint=sprint,
            crouch=crouch,
        )

    def raycast(
        self,
        distance: float = 10.0,
        *,
        origin: Vec3 | tuple[float, float, float] | None = None,
        direction: Vec3 | tuple[float, float, float] | None = None,
        layers: Iterable[CollisionLayer] | None = None,
        include_triggers: bool = True,
        exclude: Entity | None = None,
    ) -> PhysicsHit | None:
        """Raycast from the active player camera when owned by a Game."""

        game = self._owner_game()
        if game is None:
            return super().raycast(
                distance,
                origin=origin,
                direction=direction,
                layers=layers,
                include_triggers=include_triggers,
                exclude=self if exclude is None else exclude,
            )
        return super().raycast(
            distance,
            origin=game.camera.position if origin is None else origin,
            direction=game.camera.forward if direction is None else direction,
            layers=layers,
            include_triggers=include_triggers,
            exclude=self if exclude is None else exclude,
        )

    def add_weapon(
        self,
        *,
        damage: float = 25,
        cooldown: float = 0.2,
        range: float = 50,
    ) -> HitscanWeapon:
        """Create one camera-aimed hitscan weapon advanced by the Game."""

        from .game import Game
        from .gameplay import HitscanWeapon

        if hasattr(self, "weapon"):
            raise ValueError("player already has a weapon")
        game = self._owner_game()
        if not isinstance(game, Game):
            raise RuntimeError("add_weapon requires a Player owned by a Game")
        weapon = HitscanWeapon(self, damage=damage, cooldown=cooldown, range=range)
        handle = weapon._manage(
            game,
            aim=lambda: (Vec3.from_value(game.camera.position), Vec3.from_value(game.camera.forward)),
        )
        self._track_handle(handle)
        self.weapon = weapon
        return weapon

    def _owner_game(self):
        owner = self.scene._live_owner()
        return owner if owner is not None and hasattr(owner, "input") else None

    def _bind_default_controls(self) -> None:
        if self._controls_bound or not self._automatic_controls:
            return
        game = self._owner_game()
        if game is None:
            return
        from .input import Binding

        game.input.bind(
            "player_forward",
            Binding("key:w", 1.0),
            Binding("key:s", -1.0),
            Binding("key:up", 1.0),
            Binding("key:down", -1.0),
            Binding("gamepad:left_y", -1.0, 0.15),
        )
        game.input.bind(
            "player_strafe",
            Binding("key:d", 1.0),
            Binding("key:a", -1.0),
            Binding("key:right", 1.0),
            Binding("key:left", -1.0),
            Binding("gamepad:left_x", 1.0, 0.15),
        )
        game.input.bind("player_jump", "key:space", "gamepad:a")
        game.input.bind("player_sprint", "key:left_shift", "key:right_shift")
        game.input.bind("player_crouch", "key:left_ctrl", "key:right_ctrl")
        game.input.bind("player_release_mouse", "key:escape")
        game.input.bind("player_capture_mouse", "mouse:left")
        game.input.pointer_lock_requested = True
        self._controls_bound = True

    def start(self) -> None:
        self._bind_default_controls()

    def fixed_update(self, dt: float) -> None:
        if not self._automatic_controls:
            return
        self._bind_default_controls()
        game = self._owner_game()
        if game is None or not self._controls_bound:
            return
        self._yaw -= game.input.gamepad_axis("right_x") * 140.0 * dt
        self._pitch = max(
            -85.0,
            min(85.0, self._pitch + game.input.gamepad_axis("right_y") * 100.0 * dt),
        )
        movement = (
            game.input.value("player_strafe"),
            0.0,
            game.input.value("player_forward"),
        )
        jump = self._jump_requested
        self._jump_requested = False
        sprint = self._sprint_enabled and game.input.down("player_sprint")
        crouch = self._crouch_enabled and game.input.down("player_crouch")
        self.move(
            movement,
            heading_degrees=self._yaw,
            jump=jump,
            sprint=sprint,
            crouch=crouch,
        )

    def update(self, dt: float) -> None:
        del dt
        if not self._automatic_controls:
            return
        game = self._owner_game()
        if game is None or not self._controls_bound:
            return
        # Only a press edge requests a jump. Players must time the next press
        # for landing; holding Space does not create an automatic pogo stick.
        self._jump_requested = self._jump_requested or game.input.pressed(
            "player_jump"
        )
        if game.input.pressed("player_release_mouse"):
            game.input.pointer_lock_requested = False
        elif game.input.pressed("player_capture_mouse"):
            game.input.pointer_lock_requested = True
        if game.input.pointer_locked:
            pointer_x, pointer_y = game.input.pointer.delta
            self._yaw -= pointer_x * self._mouse_sensitivity
            self._pitch = max(
                -85.0,
                min(85.0, self._pitch - pointer_y * self._mouse_sensitivity),
            )

        self._sync_camera()

    def _sync_camera(self) -> None:
        """Keep the active camera usable immediately after Player construction."""

        game = self._owner_game()
        if game is None:
            return
        camera = self.scene.camera
        eye = 0.95 if self.controller.crouched else self._camera_height
        yaw_offset = self.scene._native.entity_character_yaw_offset(self._handle)
        view_yaw = self._yaw + yaw_offset
        if self.controller.mode == "first_person":
            camera.position = (self.position.x, self.position.y + eye, self.position.z)
            camera.rotation = (self._pitch, view_yaw, 0.0)
        else:
            view_rotation = Quat.from_euler((self._pitch, view_yaw, 0.0))
            target = self.position + Vec3(0.0, eye * 0.8, 0.0)
            forward = view_rotation.rotate(Vec3(0.0, 0.0, -1.0))
            camera.position = target - forward * self._third_person_distance
            camera.look_at(target)
