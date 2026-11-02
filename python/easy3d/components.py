"""Native component facades."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from os import PathLike
from typing import TYPE_CHECKING, Literal, TypeAlias

from .math import Quat, Vec3

if TYPE_CHECKING:
    from .entity import Entity

ColorValue: TypeAlias = tuple[float, float, float] | tuple[float, float, float, float]
RenderKind: TypeAlias = Literal["cube", "plane", "sphere", "model"]
LightKind: TypeAlias = Literal["ambient", "directional"]
ColliderShape: TypeAlias = Literal["box", "sphere", "capsule", "convex", "mesh"]
CollisionLayer: TypeAlias = Literal["static", "dynamic", "sensor", "character"]
RigidBodyType: TypeAlias = Literal["dynamic", "kinematic"]
CharacterMode: TypeAlias = Literal["first_person", "third_person"]


def normalize_color(value: ColorValue) -> tuple[float, float, float, float]:
    if not isinstance(value, tuple) or len(value) not in (3, 4):
        raise TypeError("color must be an (r, g, b) or (r, g, b, a) tuple")
    components = tuple(float(component) for component in value)
    if not all(math.isfinite(component) and 0 <= component <= 1 for component in components):
        raise ValueError("color components must be finite and between 0 and 1")
    if len(components) == 3:
        return components[0], components[1], components[2], 1.0
    return components  # type: ignore[return-value]


def _finite_non_negative(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _finite_positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


@dataclass(frozen=True, slots=True)
class PhysicsMaterial:
    """Per-collider Coulomb friction and bounce coefficients."""

    friction: float = 0.2
    restitution: float = 0.0

    def __post_init__(self) -> None:
        friction = _finite_non_negative(self.friction, "friction")
        restitution = float(self.restitution)
        if not math.isfinite(restitution) or not 0 <= restitution <= 1:
            raise ValueError("restitution must be finite and between 0 and 1")
        object.__setattr__(self, "friction", friction)
        object.__setattr__(self, "restitution", restitution)


class MeshRenderer:
    """Live facade for an entity's singleton native render component."""

    __slots__ = ("_entity",)

    def __init__(self, entity: Entity) -> None:
        self._entity = entity

    @property
    def entity(self) -> Entity:
        return self._entity

    def _info(
        self,
    ) -> tuple[
        str,
        tuple[float, float, float, float],
        str | None,
        bool,
        float,
        float,
        float,
        bool,
        bool,
    ]:
        info = self._entity.scene._native.render_component_info(self._entity._handle)
        return (info[0], tuple(info[1]), *info[2:])  # type: ignore[return-value]

    @property
    def kind(self) -> RenderKind:
        return self._info()[0]  # type: ignore[return-value]

    @property
    def color(self) -> tuple[float, float, float, float]:
        return self._info()[1]

    @color.setter
    def color(self, value: ColorValue) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_color(
            self._entity._handle, normalize_color(value)
        )

    @property
    def asset(self) -> Path | None:
        value = self._info()[2]
        return None if value is None else Path(value)

    @property
    def lit(self) -> bool:
        return self._info()[3]

    @lit.setter
    def lit(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("lit must be a bool")
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_lit(self._entity._handle, value)

    def _set_surface(
        self,
        *,
        metallic: float | None = None,
        roughness: float | None = None,
        emission: float | None = None,
        casts_shadows: bool | None = None,
        receives_shadows: bool | None = None,
    ) -> None:
        info = self._info()
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_surface(
            self._entity._handle,
            info[4] if metallic is None else metallic,
            info[5] if roughness is None else roughness,
            info[6] if emission is None else emission,
            info[7] if casts_shadows is None else casts_shadows,
            info[8] if receives_shadows is None else receives_shadows,
        )

    @property
    def metallic(self) -> float:
        return self._info()[4]

    @metallic.setter
    def metallic(self, value: float) -> None:
        self._set_surface(metallic=value)

    @property
    def roughness(self) -> float:
        return self._info()[5]

    @roughness.setter
    def roughness(self, value: float) -> None:
        self._set_surface(roughness=value)

    @property
    def emission(self) -> float:
        return self._info()[6]

    @emission.setter
    def emission(self, value: float) -> None:
        self._set_surface(emission=value)

    @property
    def casts_shadows(self) -> bool:
        return self._info()[7]

    @casts_shadows.setter
    def casts_shadows(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("casts_shadows must be a bool")
        self._set_surface(casts_shadows=value)

    @property
    def receives_shadows(self) -> bool:
        return self._info()[8]

    @receives_shadows.setter
    def receives_shadows(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("receives_shadows must be a bool")
        self._set_surface(receives_shadows=value)

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_render_component(self._entity._handle)


class LightComponent:
    """Live facade for an entity's singleton native light component."""

    __slots__ = ("_entity",)

    def __init__(self, entity: Entity) -> None:
        self._entity = entity

    @property
    def entity(self) -> Entity:
        return self._entity

    def _info(self) -> tuple[str, tuple[float, float, float, float], float]:
        kind, color, intensity = self._entity.scene._native.light_component_info(
            self._entity._handle
        )
        return kind, tuple(color), intensity

    @property
    def kind(self) -> LightKind:
        return self._info()[0]  # type: ignore[return-value]

    @property
    def color(self) -> tuple[float, float, float, float]:
        return self._info()[1]

    @color.setter
    def color(self, value: ColorValue) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_light_color(
            self._entity._handle, normalize_color(value)
        )

    @property
    def intensity(self) -> float:
        return self._info()[2]

    @intensity.setter
    def intensity(self, value: float) -> None:
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError("light intensity must be finite and non-negative")
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_light_intensity(self._entity._handle, result)

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_light_component(self._entity._handle)


class Collider:
    """Live facade for an entity's singleton native collider."""

    __slots__ = ("_entity",)

    def __init__(
        self,
        entity: Entity,
        *,
        shape: ColliderShape = "box",
        half_extents: Vec3 | tuple[float, float, float] = (0.5, 0.5, 0.5),
        radius: float = 0.5,
        height: float = 1.0,
        points: Iterable[Vec3 | tuple[float, float, float]] = (),
        mesh: str | PathLike[str] | None = None,
        trigger: bool = False,
        layer: CollisionLayer = "dynamic",
        material: PhysicsMaterial | None = None,
    ) -> None:
        if shape not in ("box", "sphere", "capsule", "convex", "mesh"):
            raise ValueError(
                "collider shape must be box, sphere, capsule, convex, or mesh"
            )
        if layer not in ("static", "dynamic", "sensor", "character"):
            raise ValueError(
                "collision layer must be static, dynamic, sensor, or character"
            )
        if not isinstance(trigger, bool):
            raise TypeError("trigger must be a bool")
        extents = Vec3.from_value(half_extents)
        if min(extents.x, extents.y, extents.z) <= 0:
            raise ValueError("collider half extents must be positive")
        radius_value = _finite_positive(radius, "collider radius")
        height_value = _finite_positive(height, "collider height")
        if shape == "capsule" and height_value <= 2 * radius_value:
            raise ValueError("capsule height must be greater than its diameter")
        point_values = tuple(Vec3.from_value(point) for point in points)
        mesh_path = None if mesh is None else str(Path(mesh))
        if shape == "convex" and not point_values and mesh_path is None:
            raise ValueError("convex collider requires points or a mesh asset")
        if shape == "mesh" and mesh_path is None:
            raise ValueError("mesh collider requires a mesh asset")
        if shape not in ("convex", "mesh") and (point_values or mesh_path is not None):
            raise ValueError("points/mesh are only valid for convex or mesh colliders")
        material_value = PhysicsMaterial() if material is None else material
        if not isinstance(material_value, PhysicsMaterial):
            raise TypeError("material must be an easy3d.PhysicsMaterial")
        entity.scene._require_mutable()
        entity.scene._native.add_collider_component(
            entity._handle,
            shape,
            tuple(extents),
            radius_value,
            height_value,
            [tuple(point) for point in point_values],
            mesh_path,
            trigger,
            layer,
            material_value.friction,
            material_value.restitution,
        )
        self._entity = entity

    @classmethod
    def _existing(cls, entity: Entity) -> Collider:
        component = cls.__new__(cls)
        component._entity = entity
        return component

    def _info(
        self,
    ) -> tuple[str, tuple[float, float, float], float, float, bool, str, float, float]:
        shape, extents, radius, height, trigger, layer, friction, restitution = (
            self._entity.scene._native.collider_component_info(
                self._entity._handle
            )
        )
        return shape, tuple(extents), radius, height, trigger, layer, friction, restitution

    @property
    def entity(self) -> Entity:
        return self._entity

    @property
    def shape(self) -> ColliderShape:
        return self._info()[0]  # type: ignore[return-value]

    @property
    def half_extents(self) -> Vec3:
        return Vec3(self._info()[1])

    @property
    def radius(self) -> float:
        return self._info()[2]

    @property
    def height(self) -> float:
        return self._info()[3]

    @property
    def is_trigger(self) -> bool:
        return self._info()[4]

    @property
    def layer(self) -> CollisionLayer:
        return self._info()[5]  # type: ignore[return-value]

    @property
    def material(self) -> PhysicsMaterial:
        info = self._info()
        return PhysicsMaterial(info[6], info[7])

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_collider_component(self._entity._handle)


class Rigidbody:
    """Live facade for native rigid-body motion attached to a collider."""

    __slots__ = ("_entity",)

    def __init__(
        self,
        entity: Entity,
        *,
        body_type: RigidBodyType = "dynamic",
        mass: float = 1.0,
        use_gravity: bool = True,
        continuous: bool = False,
    ) -> None:
        if body_type not in ("dynamic", "kinematic"):
            raise ValueError("body_type must be 'dynamic' or 'kinematic'")
        if not isinstance(use_gravity, bool):
            raise TypeError("use_gravity must be a bool")
        if not isinstance(continuous, bool):
            raise TypeError("continuous must be a bool")
        if continuous and body_type != "dynamic":
            raise ValueError("continuous collision detection requires a dynamic body")
        mass_value = _finite_positive(mass, "rigid body mass")
        entity.scene._require_mutable()
        entity.scene._native.add_rigid_body_component(
            entity._handle, body_type, mass_value, use_gravity, continuous
        )
        self._entity = entity

    @classmethod
    def _existing(cls, entity: Entity) -> Rigidbody:
        component = cls.__new__(cls)
        component._entity = entity
        return component

    def _info(self) -> tuple[str, float, bool, bool]:
        return self._entity.scene._native.rigid_body_component_info(
            self._entity._handle
        )

    @property
    def entity(self) -> Entity:
        return self._entity

    @property
    def body_type(self) -> RigidBodyType:
        return self._info()[0]  # type: ignore[return-value]

    @property
    def mass(self) -> float:
        return self._info()[1]

    @property
    def use_gravity(self) -> bool:
        return self._info()[2]

    @property
    def continuous(self) -> bool:
        return self._info()[3]

    @property
    def linear_velocity(self) -> Vec3:
        return Vec3(
            self._entity.scene._native.rigid_body_linear_velocity(
                self._entity._handle
            )
        )

    @linear_velocity.setter
    def linear_velocity(self, value: Vec3 | tuple[float, float, float]) -> None:
        velocity = Vec3.from_value(value)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_rigid_body_linear_velocity(
            self._entity._handle, tuple(velocity)
        )

    def add_force(self, force: Vec3 | tuple[float, float, float]) -> None:
        value = Vec3.from_value(force)
        self._entity.scene._require_mutable()
        self._entity.scene._native.add_rigid_body_force(
            self._entity._handle, tuple(value)
        )

    def add_impulse(self, impulse: Vec3 | tuple[float, float, float]) -> None:
        value = Vec3.from_value(impulse)
        self._entity.scene._require_mutable()
        self._entity.scene._native.add_rigid_body_impulse(
            self._entity._handle, tuple(value)
        )

    def teleport(
        self,
        position: Vec3 | tuple[float, float, float],
        rotation: Quat | Vec3 | tuple[float, float, float] | None = None,
    ) -> None:
        target_position = Vec3.from_value(position)
        if rotation is None:
            target_rotation = self._entity.quaternion
        elif isinstance(rotation, Quat):
            target_rotation = rotation
        else:
            target_rotation = Quat.from_euler(rotation)
        self._entity.scene._require_mutable()
        self._entity.scene._native.teleport_rigid_body(
            self._entity._handle,
            tuple(target_position),
            tuple(target_rotation),
        )

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_rigid_body_component(self._entity._handle)


class CharacterController:
    """Native capsule motor with slope, step, jump, and grounded handling."""

    __slots__ = ("_entity",)

    def __init__(
        self,
        entity: Entity,
        *,
        mode: CharacterMode = "first_person",
        radius: float = 0.4,
        height: float = 1.8,
        speed: float = 5.0,
        acceleration: float = 30.0,
        air_control: float = 0.25,
        jump_speed: float = 5.0,
        max_slope_degrees: float = 50.0,
        step_height: float = 0.4,
    ) -> None:
        if mode not in ("first_person", "third_person"):
            raise ValueError("mode must be 'first_person' or 'third_person'")
        radius_value = _finite_positive(radius, "character radius")
        height_value = _finite_positive(height, "character height")
        if height_value <= 2 * radius_value:
            raise ValueError("character height must be greater than its diameter")
        speed_value = _finite_non_negative(speed, "character speed")
        acceleration_value = _finite_non_negative(
            acceleration, "character acceleration"
        )
        air_control_value = float(air_control)
        if not math.isfinite(air_control_value) or not 0 <= air_control_value <= 1:
            raise ValueError("air_control must be finite and between 0 and 1")
        jump_speed_value = _finite_non_negative(jump_speed, "jump_speed")
        slope_value = float(max_slope_degrees)
        if not math.isfinite(slope_value) or not 0 <= slope_value < 90:
            raise ValueError("max_slope_degrees must be finite and in [0, 90)")
        step_value = _finite_non_negative(step_height, "step_height")
        entity.scene._require_mutable()
        entity.scene._native.add_character_controller_component(
            entity._handle,
            mode,
            radius_value,
            height_value,
            speed_value,
            acceleration_value,
            air_control_value,
            jump_speed_value,
            slope_value,
            step_value,
        )
        self._entity = entity

    @classmethod
    def _existing(cls, entity: Entity) -> CharacterController:
        component = cls.__new__(cls)
        component._entity = entity
        return component

    def _info(self) -> tuple[str, float, float, float, float, float, float, float, float]:
        return self._entity.scene._native.character_controller_component_info(
            self._entity._handle
        )

    @property
    def entity(self) -> Entity:
        return self._entity

    @property
    def mode(self) -> CharacterMode:
        return self._info()[0]  # type: ignore[return-value]

    @property
    def radius(self) -> float:
        return self._info()[1]

    @property
    def height(self) -> float:
        return self._info()[2]

    @property
    def speed(self) -> float:
        return self._info()[3]

    @property
    def acceleration(self) -> float:
        return self._info()[4]

    @property
    def air_control(self) -> float:
        return self._info()[5]

    @property
    def jump_speed(self) -> float:
        return self._info()[6]

    @property
    def max_slope_degrees(self) -> float:
        return self._info()[7]

    @property
    def step_height(self) -> float:
        return self._info()[8]

    def _state(self) -> tuple[object, object, object, object, bool]:
        return self._entity.scene._native.character_state(self._entity._handle)

    @property
    def linear_velocity(self) -> Vec3:
        return Vec3(self._state()[2])  # type: ignore[arg-type]

    @property
    def ground_normal(self) -> Vec3:
        return Vec3(self._state()[3])  # type: ignore[arg-type]

    @property
    def grounded(self) -> bool:
        return self._state()[4]

    def set_input(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
    ) -> None:
        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_character_input(
            self._entity._handle, tuple(value), heading, jump
        )

    def set_sequenced_input(
        self,
        sequence: int,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
    ) -> None:
        """Apply one strictly newer prediction input to the native motor."""

        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise TypeError("sequence must be an integer")
        if sequence < 1 or sequence > (1 << 64) - 1:
            raise ValueError("sequence must be between 1 and 2^64 - 1")
        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_character_sequenced_input(
            self._entity._handle, sequence, tuple(value), heading, jump
        )

    @property
    def last_input_sequence(self) -> int:
        """Last sequenced input accepted by the native motor, or zero."""

        return self._entity.scene._native.character_input_sequence(
            self._entity._handle
        )

    def correct_state(
        self,
        position: Vec3 | tuple[float, float, float],
        rotation: Quat | tuple[float, float, float, float],
        linear_velocity: Vec3 | tuple[float, float, float],
    ) -> None:
        """Restore one authoritative native motor state for reconciliation."""

        target_position = Vec3.from_value(position)
        target_rotation = rotation if isinstance(rotation, Quat) else Quat(rotation)
        target_velocity = Vec3.from_value(linear_velocity)
        self._entity.scene._require_mutable()
        self._entity.scene._native.correct_character(
            self._entity._handle,
            tuple(target_position),
            tuple(target_rotation),
            tuple(target_velocity),
        )

    def replay_input(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
        delta_seconds: float,
    ) -> None:
        """Replay one validated tick without advancing the rest of the scene."""

        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        heading = float(heading_degrees)
        delta = float(delta_seconds)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        if not math.isfinite(delta) or delta <= 0:
            raise ValueError("delta_seconds must be finite and positive")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.replay_character_input(
            self._entity._handle, tuple(value), heading, jump, delta
        )

    def teleport(
        self,
        position: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
    ) -> None:
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(position)
        self._entity.scene._require_mutable()
        self._entity.scene._native.teleport_character(
            self._entity._handle, tuple(value), heading
        )

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_character_controller_component(
            self._entity._handle
        )
