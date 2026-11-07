"""Python entity references backed by generation-checked native handles."""

from __future__ import annotations

from collections.abc import Iterable
import math
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast, overload

from ._rix import EntityHandle, _camera_look_at
from .math import Quat, Vec3

if TYPE_CHECKING:
    from .components import CollisionLayer, CullMode, MeshRenderer
    from .game import CallbackHandle
    from .gameplay import Health
    from .physics import PhysicsHit
    from .scene import Scene
    from .utilities import AnimationSelection, Easing, StateMachine, Tween

_ComponentT = TypeVar("_ComponentT")


class Entity:
    """A safe reference to an entity owned by exactly one :class:`Scene`.

    Entity data lives in the native scene registry. Destroying an entity or
    clearing its scene invalidates every wrapper that carries the old handle;
    subsequent property access raises :class:`rix.InvalidEntityError`.
    """

    if TYPE_CHECKING:
        health: Health
        state_machine: StateMachine
        animations: AnimationSelection
        _managed_handles: list[CallbackHandle]
        _property_animations: dict[str, CallbackHandle]

    def __init__(
        self,
        name: str = "Entity",
        *,
        parent: Entity | None = None,
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        from .scene import Scene

        if parent is not None and not isinstance(parent, Entity):
            raise TypeError("parent must be an rix.Entity or None")
        if parent is not None and scene is not None and parent.scene is not scene:
            raise ValueError("parent and scene must belong to the same scene")
        owner = parent.scene if parent is not None else (
            scene if scene is not None else Scene.current()
        )
        if not isinstance(owner, Scene):
            raise TypeError("scene must be an rix.Scene")
        self._scene = owner
        self._handle = owner._create_handle(name)
        from .utilities import AnimationSelection

        self.animations = AnimationSelection()
        owner._register_script_entity(self)
        try:
            if parent is not None:
                self.set_parent(parent)
            self.velocity = velocity
            self.acceleration = acceleration
            self.angular_velocity = angular_velocity
            self.angular_acceleration = angular_acceleration
        except Exception:
            owner._rollback_entity_construction(self)
            raise

    @classmethod
    def _from_handle(cls, scene: Scene, handle: EntityHandle) -> Entity:
        entity = cls.__new__(cls)
        entity._scene = scene
        entity._handle = handle
        return entity

    @property
    def id(self) -> int:
        """Generation-qualified identifier unique within this entity's scene."""

        return self._handle.id

    @property
    def scene(self) -> Scene:
        return self._scene

    @property
    def is_alive(self) -> bool:
        return not self._scene.closed and self._scene._native.is_alive(self._handle)

    @property
    def name(self) -> str:
        return self._scene._native.entity_name(self._handle)

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("entity name must be a string")
        self._scene._require_mutable()
        self._scene._native.set_entity_name(self._handle, value)

    @property
    def enabled(self) -> bool:
        return self._scene._native.entity_enabled(self._handle)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("enabled must be a bool")
        self._scene._require_mutable()
        self._scene._native.set_entity_enabled(self._handle, value)

    @property
    def visible(self) -> bool:
        return self._scene._native.entity_visible(self._handle)

    @visible.setter
    def visible(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("visible must be a bool")
        self._scene._require_mutable()
        self._scene._native.set_entity_visible(self._handle, value)

    def _require_mesh_renderer(self) -> MeshRenderer:
        from .components import MeshRenderer

        renderer = self.get_component(MeshRenderer)
        if renderer is None:
            raise AttributeError("entity does not have a MeshRenderer component")
        return renderer

    @property
    def cull_mode(self) -> CullMode:
        """Face-culling mode shared with this entity's native MeshRenderer."""

        return self._require_mesh_renderer().cull_mode

    @cull_mode.setter
    def cull_mode(self, value: CullMode) -> None:
        self._require_mesh_renderer().cull_mode = value

    @property
    def double_sided(self) -> bool:
        return self._require_mesh_renderer().double_sided

    @double_sided.setter
    def double_sided(self, value: bool) -> None:
        self._require_mesh_renderer().double_sided = value

    @property
    def position(self) -> Vec3:
        """Live local-space position. Component assignment persists natively."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_local_position(self._handle)),
            self._set_position,
        )

    @position.setter
    def position(self, value: Vec3 | tuple[float, float, float]) -> None:
        vector = Vec3.from_value(value)
        self._scene._require_mutable()
        self._scene._native.set_entity_local_position(self._handle, *vector)

    @property
    def x(self) -> float:
        return self.position.x

    @x.setter
    def x(self, value: float) -> None:
        self.position.x = value

    @property
    def y(self) -> float:
        return self.position.y

    @y.setter
    def y(self, value: float) -> None:
        self.position.y = value

    @property
    def z(self) -> float:
        return self.position.z

    @z.setter
    def z(self, value: float) -> None:
        self.position.z = value

    def _set_position(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_local_position(self._handle, *value)

    @property
    def rotation(self) -> Vec3:
        """Live local Euler rotation in degrees (internally a quaternion).

        Explicitly authored angles remain continuous across quaternion Euler
        singularities, so operations such as ``entity.ry += 1`` can rotate
        through any number of complete turns.
        """

        def get_euler() -> tuple[float, float, float]:
            rotation = Quat(
                self._scene._native.entity_local_rotation(self._handle)
            )
            return tuple(self._scene._entity_euler(self._handle, rotation))

        def set_euler(value: tuple[float, float, float]) -> None:
            self._set_rotation(value)

        return Vec3._live(get_euler, set_euler)

    @rotation.setter
    def rotation(self, value: Vec3 | tuple[float, float, float]) -> None:
        self._set_rotation(tuple(Vec3.from_value(value)))

    def _set_rotation(self, value: tuple[float, float, float]) -> None:
        euler = Vec3(value)
        rotation = Quat.from_euler(euler)
        self._scene._require_mutable()
        self._scene._native.set_entity_local_rotation(self._handle, *rotation)
        self._scene._remember_entity_rotation(self._handle, euler, rotation)

    @property
    def rx(self) -> float:
        return self.rotation.x

    @rx.setter
    def rx(self, value: float) -> None:
        self.rotation.x = value

    @property
    def ry(self) -> float:
        return self.rotation.y

    @ry.setter
    def ry(self, value: float) -> None:
        self.rotation.y = value

    @property
    def rz(self) -> float:
        return self.rotation.z

    @rz.setter
    def rz(self, value: float) -> None:
        self.rotation.z = value

    @property
    def quaternion(self) -> Quat:
        return Quat(self._scene._native.entity_local_rotation(self._handle))

    @quaternion.setter
    def quaternion(self, value: Quat) -> None:
        if not isinstance(value, Quat):
            raise TypeError("quaternion must be an rix.Quat")
        self._scene._require_mutable()
        self._scene._native.set_entity_local_rotation(self._handle, *value)
        self._scene._remember_entity_rotation(
            self._handle,
            value.to_euler(),
            value,
        )

    @property
    def scale(self) -> Vec3:
        """Live local-space scale. Scale components must remain nonzero."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_local_scale(self._handle)),
            self._set_scale,
        )

    @scale.setter
    def scale(self, value: float | Vec3 | tuple[float, float, float]) -> None:
        vector = (
            Vec3(float(value), float(value), float(value))
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else Vec3.from_value(value)  # type: ignore[arg-type]
        )
        self._scene._require_mutable()
        self._scene._native.set_entity_local_scale(self._handle, *vector)

    def _set_scale(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_local_scale(self._handle, *value)

    def _world_components(self) -> tuple[tuple[float, float, float], tuple[float, float, float, float], tuple[float, float, float]]:
        position, rotation, scale = self._scene._native.entity_world_transform(self._handle)
        return tuple(position), tuple(rotation), tuple(scale)

    @property
    def world_position(self) -> Vec3:
        return Vec3(self._world_components()[0])

    @property
    def world_quaternion(self) -> Quat:
        return Quat(self._world_components()[1])

    @property
    def world_rotation(self) -> Vec3:
        return self.world_quaternion.to_euler()

    @property
    def world_scale(self) -> Vec3:
        return Vec3(self._world_components()[2])

    @property
    def velocity(self) -> Vec3:
        """Live world-space velocity in world units per second."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_velocity(self._handle)),
            self._set_velocity,
        )

    @velocity.setter
    def velocity(self, value: Vec3 | tuple[float, float, float]) -> None:
        self._set_velocity(tuple(Vec3.from_value(value)))

    def _set_velocity(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_velocity(self._handle, value)

    @property
    def acceleration(self) -> Vec3:
        """Live additive world-space acceleration in units per second squared."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_acceleration(self._handle)),
            self._set_acceleration,
        )

    @acceleration.setter
    def acceleration(self, value: Vec3 | tuple[float, float, float]) -> None:
        self._set_acceleration(tuple(Vec3.from_value(value)))

    def _set_acceleration(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_acceleration(self._handle, value)

    @property
    def angular_velocity(self) -> Vec3:
        """Live world-axis angular velocity in degrees per second."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_angular_velocity(self._handle)),
            self._set_angular_velocity,
        )

    @angular_velocity.setter
    def angular_velocity(self, value: Vec3 | tuple[float, float, float]) -> None:
        self._set_angular_velocity(tuple(Vec3.from_value(value)))

    def _set_angular_velocity(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_angular_velocity(self._handle, value)

    @property
    def angular_acceleration(self) -> Vec3:
        """Live world-axis angular acceleration in degrees per second squared."""

        return Vec3._live(
            lambda: tuple(
                self._scene._native.entity_angular_acceleration(self._handle)
            ),
            self._set_angular_acceleration,
        )

    @angular_acceleration.setter
    def angular_acceleration(
        self, value: Vec3 | tuple[float, float, float]
    ) -> None:
        self._set_angular_acceleration(tuple(Vec3.from_value(value)))

    def _set_angular_acceleration(
        self, value: tuple[float, float, float]
    ) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_angular_acceleration(self._handle, value)

    @property
    def speed(self) -> float:
        return self.velocity.length

    @speed.setter
    def speed(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("speed must be a number")
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError("speed must be finite and non-negative")
        current = Vec3(self.velocity)
        direction = self.forward if current.length <= 1.0e-12 else current.normalized()
        self.velocity = direction * result

    @property
    def movement_direction(self) -> Vec3:
        value = Vec3(self.velocity)
        return Vec3() if value.length <= 1.0e-12 else value.normalized()

    @property
    def forward(self) -> Vec3:
        return self.world_quaternion.rotate((0, 0, -1))

    @property
    def right(self) -> Vec3:
        return self.world_quaternion.rotate((1, 0, 0))

    @property
    def up(self) -> Vec3:
        return self.world_quaternion.rotate((0, 1, 0))

    def local_to_world_direction(
        self, direction: Vec3 | tuple[float, float, float]
    ) -> Vec3:
        return self.world_quaternion.rotate(Vec3.from_value(direction))

    def world_to_local_direction(
        self, direction: Vec3 | tuple[float, float, float]
    ) -> Vec3:
        return self.world_quaternion.conjugate().rotate(Vec3.from_value(direction))

    def face_direction(
        self,
        direction: Vec3 | tuple[float, float, float],
        *,
        up: Vec3 | tuple[float, float, float] = (0, 1, 0),
    ) -> Entity:
        value = Vec3.from_value(direction)
        if value.length <= 1.0e-12:
            raise ValueError("direction must not be zero length")
        return self.look_at(self.world_position + value, up=up)

    def launch(
        self,
        direction: Vec3 | tuple[float, float, float],
        speed: float,
        *,
        face: bool = False,
    ) -> Entity:
        value = Vec3.from_value(direction)
        if value.length <= 1.0e-12:
            raise ValueError("direction must not be zero length")
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            raise TypeError("speed must be a number")
        speed_value = float(speed)
        if not math.isfinite(speed_value) or speed_value < 0:
            raise ValueError("speed must be finite and non-negative")
        if face:
            self.face_direction(value)
        self.velocity = value.normalized() * speed_value
        return self

    @property
    def parent(self) -> Entity | None:
        handle = self._scene._native.entity_parent(self._handle)
        return None if handle is None else Entity._from_handle(self._scene, handle)

    @parent.setter
    def parent(self, value: Entity | None) -> None:
        self.set_parent(value)

    @property
    def children(self) -> tuple[Entity, ...]:
        return tuple(
            Entity._from_handle(self._scene, handle)
            for handle in self._scene._native.entity_children(self._handle)
        )

    def set_parent(self, parent: Entity | None, *, keep_world: bool = False) -> None:
        if parent is not None and not isinstance(parent, Entity):
            raise TypeError("parent must be an rix.Entity or None")
        if parent is not None and parent.scene is not self._scene:
            raise ValueError("parent belongs to a different scene")
        self._scene._require_mutable()
        self._scene._native.set_entity_parent(
            self._handle,
            None if parent is None else parent._handle,
            bool(keep_world),
        )

    @overload
    def move(
        self,
        offset: Vec3 | tuple[float, float, float],
        *,
        local: bool = False,
    ) -> Entity: ...

    @overload
    def move(
        self, x: float, y: float, z: float, *, local: bool = False
    ) -> Entity: ...

    def move(
        self,
        offset_or_x: Vec3 | tuple[float, float, float] | float,
        y: float | None = None,
        z: float | None = None,
        *,
        local: bool = False,
    ) -> Entity:
        """Move by a tuple/vector or three scalars, optionally in local space."""

        if y is None and z is None and not isinstance(offset_or_x, (int, float)):
            value = Vec3.from_value(offset_or_x)
        elif y is not None and z is not None and isinstance(offset_or_x, (int, float)):
            value = Vec3(offset_or_x, y, z)
        else:
            raise TypeError("move expects a vector/tuple or exactly three numbers")
        if local:
            value = self.quaternion.rotate(value)
        self.position = self.position + value
        return self

    @overload
    def rotate(self, euler_degrees: Vec3 | tuple[float, float, float]) -> Entity: ...

    @overload
    def rotate(self, rx: float, ry: float, rz: float) -> Entity: ...

    def rotate(
        self,
        rotation_or_x: Vec3 | tuple[float, float, float] | float,
        y: float | None = None,
        z: float | None = None,
    ) -> Entity:
        """Rotate by an Euler tuple/vector or three degree values."""

        if y is None and z is None and not isinstance(rotation_or_x, (int, float)):
            value = Vec3.from_value(rotation_or_x)
        elif y is not None and z is not None and isinstance(rotation_or_x, (int, float)):
            value = Vec3(rotation_or_x, y, z)
        else:
            raise TypeError("rotate expects a vector/tuple or exactly three numbers")
        self.rotation = self.rotation + value
        return self

    def look_at(
        self,
        target: Entity | Vec3 | tuple[float, float, float],
        *,
        up: Vec3 | tuple[float, float, float] = (0, 1, 0),
    ) -> Entity:
        """Orient the entity's -Z axis toward an entity or world-space point."""

        target_position = (
            target.world_position if isinstance(target, Entity) else Vec3.from_value(target)
        )
        if isinstance(target, Entity) and target.scene is not self.scene:
            raise ValueError("target belongs to a different scene")
        position = self.world_position
        up_value = Vec3.from_value(up)
        world_rotation = Quat(
            _camera_look_at(
                position.x,
                position.y,
                position.z,
                target_position.x,
                target_position.y,
                target_position.z,
                up_value.x,
                up_value.y,
                up_value.z,
            )
        )
        parent = self.parent
        local_rotation = (
            world_rotation
            if parent is None
            else (parent.world_quaternion.conjugate() * world_rotation).normalized()
        )
        from .components import CharacterController, Rigidbody

        if self.get_component(Rigidbody) is not None or self.get_component(
            CharacterController
        ) is not None:
            self.teleport(position, world_rotation)
        else:
            self.quaternion = local_rotation
        return self

    def distance_to(self, target: Entity | Vec3 | tuple[float, float, float]) -> float:
        """Return world-space distance to an entity or point."""

        if isinstance(target, Entity):
            if target.scene is not self.scene:
                raise ValueError("target belongs to a different scene")
            target_position = target.world_position
        else:
            target_position = Vec3.from_value(target)
        return (target_position - self.world_position).length

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
        """Raycast from this entity along its forward direction."""

        from .physics import raycast

        return raycast(
            self.scene,
            self.world_position if origin is None else origin,
            self.world_quaternion.rotate((0, 0, -1)) if direction is None else direction,
            distance,
            layers=layers,
            include_triggers=include_triggers,
            exclude=self if exclude is None else exclude,
        )

    def show(self) -> Entity:
        self.visible = True
        return self

    def hide(self) -> Entity:
        self.visible = False
        return self

    def enable(self) -> Entity:
        self.enabled = True
        return self

    def disable(self) -> Entity:
        self.enabled = False
        return self

    def destroy_after(self, seconds: float):
        """Destroy after render/game-loop time and return a cancellation handle."""

        owner = self.scene._live_owner()
        from .game import Game

        if not isinstance(owner, Game):
            raise RuntimeError("destroy_after requires an entity owned by a Game")

        def destroy_if_alive() -> None:
            if self.is_alive:
                self.destroy()

        return owner.after(seconds, destroy_if_alive)

    def teleport(
        self,
        position: Vec3 | tuple[float, float, float],
        rotation: Quat | Vec3 | tuple[float, float, float] | None = None,
        *,
        reset_motion: bool = False,
    ) -> Entity:
        """Teleport through the owning native component when physics owns motion."""

        from .components import CharacterController, Rigidbody

        rigid_body = self.get_component(Rigidbody)
        if rigid_body is not None:
            rigid_body.teleport(position, rotation, reset_motion=reset_motion)
            return self
        character = self.get_component(CharacterController)
        if character is not None:
            if isinstance(rotation, Quat):
                heading = rotation.to_euler().y
            elif rotation is None:
                heading = self.rotation.y
            else:
                heading = Vec3.from_value(rotation).y
            character.teleport(
                position,
                heading_degrees=heading,
                reset_motion=reset_motion,
            )
            return self
        self.position = position
        if rotation is not None:
            if isinstance(rotation, Quat):
                self.quaternion = rotation
            else:
                self.rotation = rotation
        if reset_motion:
            self._scene._native.reset_entity_motion(self._handle)
        return self

    def on_enter(
        self, callback: Callable[[Entity], None]
    ) -> Callable[[Entity], None]:
        """Register a trigger-enter decorator callback receiving the other entity."""

        if not callable(callback):
            raise TypeError("trigger callback must be callable")

        def dispatch(event: object) -> None:
            callback(cast(Any, event).other)

        self.on_trigger_enter = dispatch  # type: ignore[attr-defined]
        self.scene._register_script_entity(self)
        return callback

    def on_exit(
        self, callback: Callable[[Entity], None]
    ) -> Callable[[Entity], None]:
        """Register a trigger-exit decorator callback receiving the other entity."""

        if not callable(callback):
            raise TypeError("trigger callback must be callable")

        def dispatch(event: object) -> None:
            callback(cast(Any, event).other)

        self.on_trigger_exit = dispatch  # type: ignore[attr-defined]
        self.scene._register_script_entity(self)
        return callback

    def destroy(self) -> None:
        """Destroy this entity and invalidate all wrappers to its handle."""

        self._scene._destroy_entity(self)

    def _track_handle(self, handle: CallbackHandle) -> CallbackHandle:
        handles = getattr(self, "_managed_handles", None)
        if handles is None:
            handles = []
            self._managed_handles = handles
        handles.append(handle)
        return handle

    def _cancel_managed(self) -> None:
        handles = getattr(self, "_managed_handles", ())
        for handle in tuple(handles):
            handle.cancel()
        if handles:
            handles.clear()
        animations = getattr(self, "_property_animations", None)
        if animations is not None:
            animations.clear()

    def add_health(
        self,
        maximum: float = 100,
        *,
        current: float | None = None,
        invulnerable: bool = False,
    ) -> Health:
        """Attach and return this entity's one canonical Health object."""

        from .gameplay import Health

        return Health(self, maximum, current=current, invulnerable=invulnerable)

    def add_state_machine(self, machine: StateMachine) -> StateMachine:
        """Attach an already configured state machine to the owning Game."""

        from .game import Game
        from .utilities import StateMachine

        if not isinstance(machine, StateMachine):
            raise TypeError("machine must be an rix.StateMachine")
        if hasattr(self, "_state_machine"):
            raise ValueError("entity already has a state machine")
        owner = self.scene._live_owner()
        if not isinstance(owner, Game):
            raise RuntimeError("managed state machines require an entity owned by a Game")
        self.scene._register_managed_entity(self)
        self._track_handle(
            owner.manage_state_machine(
                machine,
                active=lambda: self.is_alive and self.enabled and self.scene.active,
            )
        )
        machine.bind_animations(self.animations)
        self._state_machine = machine
        self.states = machine
        return machine

    def state_machine(self, initial: str) -> StateMachine:
        """Create and attach an automatically advanced state machine."""

        from .utilities import StateMachine

        return self.add_state_machine(StateMachine(initial))

    def animate(
        self,
        property_name: str,
        *,
        to: float | Vec3 | tuple[float, float, float],
        duration: float,
        easing: Easing | str | Callable[[float], float] = "linear",
        loop: bool = False,
        ping_pong: bool = False,
    ) -> Tween[Any]:
        """Animate a validated transform property through the existing Tween."""

        from .game import Game
        from .utilities import Tween

        allowed = {"x", "y", "z", "rx", "ry", "rz", "position", "rotation", "scale"}
        if property_name not in allowed:
            raise ValueError(
                "animatable property must be x, y, z, rx, ry, rz, position, rotation, or scale"
            )
        owner = self.scene._live_owner()
        if not isinstance(owner, Game):
            raise RuntimeError("animate requires an entity owned by a Game")
        animations = getattr(self, "_property_animations", None)
        if animations is None:
            animations = {}
            self._property_animations = animations
        previous = animations.pop(property_name, None)
        if previous is not None:
            previous.cancel()
        start = getattr(self, property_name)
        if property_name in {"position", "rotation", "scale"}:
            target = (
                Vec3(float(to), float(to), float(to))
                if property_name == "scale" and isinstance(to, (int, float))
                else Vec3.from_value(cast(Iterable[float], to))
            )
        else:
            target = float(cast(float, to))
        tween: Tween[Any] = Tween(
            start,
            target,
            duration,
            easing=easing,
            loop=loop,
            ping_pong=ping_pong,
            autostart=True,
            time_domain="render",
            on_update=lambda value: setattr(self, property_name, value),
        )
        handle = owner.manage_tween(tween)
        animations[property_name] = handle
        self._track_handle(handle)
        return tween

    def add_component(
        self, component_type: type[_ComponentT], **kwargs: Any
    ) -> _ComponentT:
        """Attach a supported singleton component and return its live facade."""

        from .components import CharacterController, Collider, Rigidbody

        if component_type is Collider:
            return cast(_ComponentT, Collider(self, **kwargs))
        if component_type is Rigidbody:
            return cast(_ComponentT, Rigidbody(self, **kwargs))
        if component_type is CharacterController:
            return cast(_ComponentT, CharacterController(self, **kwargs))
        raise TypeError("unsupported component type for add_component")

    def has_component(self, component_type: type[_ComponentT]) -> bool:
        from .components import CharacterController, Collider, LightComponent, MeshRenderer, Rigidbody

        if component_type is MeshRenderer:
            return self._scene._native.has_render_component(self._handle)
        if component_type is LightComponent:
            return self._scene._native.has_light_component(self._handle)
        if component_type is Collider:
            return self._scene._native.has_collider_component(self._handle)
        if component_type is Rigidbody:
            return self._scene._native.has_rigid_body_component(self._handle)
        if component_type is CharacterController:
            return self._scene._native.has_character_controller_component(self._handle)
        raise TypeError("unsupported component type")

    def get_component(self, component_type: type[_ComponentT]) -> _ComponentT | None:
        from .components import CharacterController, Collider, LightComponent, MeshRenderer, Rigidbody

        if component_type is MeshRenderer:
            return (
                cast(_ComponentT, MeshRenderer(self))
                if self.has_component(MeshRenderer)
                else None
            )
        if component_type is LightComponent:
            return (
                cast(_ComponentT, LightComponent(self))
                if self.has_component(LightComponent)
                else None
            )
        if component_type is Collider:
            return (
                cast(_ComponentT, Collider._existing(self))
                if self.has_component(Collider)
                else None
            )
        if component_type is Rigidbody:
            return (
                cast(_ComponentT, Rigidbody._existing(self))
                if self.has_component(Rigidbody)
                else None
            )
        if component_type is CharacterController:
            return (
                cast(_ComponentT, CharacterController._existing(self))
                if self.has_component(CharacterController)
                else None
            )
        raise TypeError("unsupported component type")

    def remove_component(self, component_type: type[_ComponentT]) -> None:
        component = self.get_component(component_type)
        if component is None:
            raise ValueError("entity does not have the requested component")
        cast(Any, component).remove()

    def __repr__(self) -> str:
        if not self.is_alive:
            return f"Entity(id={self.id}, destroyed=True)"
        return f"Entity(name={self.name!r}, id={self.id})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self._scene is other._scene and self._handle == other._handle

    def __hash__(self) -> int:
        return hash((id(self._scene), self._handle.world_id, self.id))
