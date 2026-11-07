"""Native component facades."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from os import PathLike
from typing import TYPE_CHECKING, Literal, TypeAlias

from .math import Quat, Vec3
from .autotexture import (
    OptionalMap,
    TextureFilter,
    TextureMode,
    prepare_textures,
    validate_pixels_per_unit,
    validate_texture_filter,
    validate_texture_mode,
)

if TYPE_CHECKING:
    from .entity import Entity

ColorValue: TypeAlias = (
    str | tuple[float, float, float] | tuple[float, float, float, float]
)
RenderKind: TypeAlias = Literal["cube", "plane", "sphere", "model"]
CullMode: TypeAlias = Literal["back", "front", "none"]
LightKind: TypeAlias = Literal["ambient", "directional", "point", "spot"]
ColliderShape: TypeAlias = Literal["box", "sphere", "capsule", "convex", "mesh"]
CollisionLayer: TypeAlias = Literal["static", "dynamic", "sensor", "character"]
RigidBodyType: TypeAlias = Literal["dynamic", "kinematic"]
CharacterMode: TypeAlias = Literal["first_person", "third_person"]


def validate_cull_mode(value: str) -> CullMode:
    if value not in ("back", "front", "none"):
        raise ValueError("cull_mode must be 'back', 'front', or 'none'")
    return value  # type: ignore[return-value]


def resolve_cull_mode(
    cull_mode: CullMode | None,
    double_sided: bool | None,
) -> CullMode:
    if double_sided is not None and not isinstance(double_sided, bool):
        raise TypeError("double_sided must be a bool")
    resolved = "back" if cull_mode is None else validate_cull_mode(cull_mode)
    if double_sided is None:
        return resolved
    shorthand: CullMode = "none" if double_sided else "back"
    if cull_mode is not None and resolved != shorthand:
        raise ValueError(
            f"double_sided={double_sided!r} conflicts with cull_mode={cull_mode!r}"
        )
    return shorthand


def normalize_color(value: ColorValue) -> tuple[float, float, float, float]:
    if isinstance(value, str):
        named = {
            "black": "#000000",
            "white": "#ffffff",
            "red": "#ff0000",
            "green": "#00aa44",
            "blue": "#0066ff",
            "yellow": "#ffdd00",
            "orange": "#ff8800",
            "purple": "#8844cc",
            "pink": "#ff66aa",
            "cyan": "#00cccc",
            "skyblue": "#87ceeb",
            "lightblue": "#add8e6",
            "gray": "#808080",
            "grey": "#808080",
        }
        text = named.get(value.strip().lower(), value.strip())
        if not text.startswith("#") or len(text) not in (7, 9):
            raise ValueError(
                "color string must be a known name or #RRGGBB/#RRGGBBAA"
            )
        try:
            channels = tuple(
                int(text[index : index + 2], 16) / 255.0
                for index in range(1, len(text), 2)
            )
        except ValueError as error:
            raise ValueError("hex color contains non-hexadecimal digits") from error
        if len(channels) == 3:
            return channels[0], channels[1], channels[2], 1.0
        return channels  # type: ignore[return-value]
    if not isinstance(value, tuple) or len(value) not in (3, 4):
        raise TypeError(
            "color must be a name, hex string, or (r, g, b)/(r, g, b, a) tuple"
        )
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
        float,
        str,
        str,
        float,
        bool,
        str | None,
        str | None,
        str | None,
        str | None,
        str | None,
        tuple[float, float, float],
        str,
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
    def texture(self) -> Path | None:
        if self.kind == "model":
            return None
        return self.asset

    @texture.setter
    def texture(self, value: str | PathLike[str] | None) -> None:
        self._apply_texture(texture=value)

    def _map_path(self, index: int) -> Path | None:
        value = self._info()[index]
        return None if value is None else Path(value)

    def _apply_texture(
        self,
        *,
        texture: str | PathLike[str] | None | object = ...,
        pixels_per_unit: float | None = None,
        texture_filter: TextureFilter | None = None,
        texture_mode: TextureMode | None = None,
        normal_map: OptionalMap | object = ...,
        roughness_map: OptionalMap | object = ...,
        metallic_map: OptionalMap | object = ...,
        emissive_map: OptionalMap | object = ...,
        ambient_occlusion_map: OptionalMap | object = ...,
        normal_strength: float | None = None,
        hot_reload: bool | None = None,
    ) -> None:
        info = self._info()
        kind = info[0]
        if kind == "model":
            raise NotImplementedError(
                "runtime material overrides for imported models are not yet supported"
            )
        base = info[2] if texture is ... else texture
        density = validate_pixels_per_unit(
            info[9] if pixels_per_unit is None else pixels_per_unit
        )
        filtering = validate_texture_filter(
            info[10] if texture_filter is None else texture_filter
        )
        mode = validate_texture_mode(info[11] if texture_mode is None else texture_mode)
        strength = info[12] if normal_strength is None else float(normal_strength)
        if not math.isfinite(strength) or not 0 <= strength <= 8:
            raise ValueError("normal_strength must be finite and in [0, 8]")
        reload_enabled = info[13] if hot_reload is None else hot_reload
        if not isinstance(reload_enabled, bool):
            raise TypeError("texture_hot_reload must be a bool")
        old_maps = tuple(self._map_path(index) for index in range(14, 19))
        if texture is not ... and base is not None:
            # Material maps belong to their base texture. Replacing that base
            # rediscovers companions instead of accidentally retaining maps
            # from the previous filename.
            maps: tuple[OptionalMap, ...] = (
                None if normal_map is ... else normal_map,  # type: ignore[arg-type]
                None if roughness_map is ... else roughness_map,  # type: ignore[arg-type]
                None if metallic_map is ... else metallic_map,  # type: ignore[arg-type]
                None if emissive_map is ... else emissive_map,  # type: ignore[arg-type]
                None
                if ambient_occlusion_map is ...
                else ambient_occlusion_map,  # type: ignore[arg-type]
            )
        else:
            maps = (
                old_maps[0] if normal_map is ... else normal_map,  # type: ignore[arg-type]
                old_maps[1] if roughness_map is ... else roughness_map,  # type: ignore[arg-type]
                old_maps[2] if metallic_map is ... else metallic_map,  # type: ignore[arg-type]
                old_maps[3] if emissive_map is ... else emissive_map,  # type: ignore[arg-type]
                old_maps[4]
                if ambient_occlusion_map is ...
                else ambient_occlusion_map,  # type: ignore[arg-type]
            )
        if base is None and texture is not ...:
            # Clearing the base texture clears dependent maps atomically. A map
            # cannot remain meaningful without the UV/color resource that owns
            # its material configuration.
            maps = (False, False, False, False, False)
        scale = self._entity.world_scale
        stored_atlas_dimensions = tuple(info[19])
        starts_new_atlas_layout = texture is not ... or (
            texture_mode is not None and mode == "atlas" and info[11] != "atlas"
        )
        atlas_dimensions = (
            (abs(scale.x), abs(scale.y), abs(scale.z))
            if starts_new_atlas_layout
            else stored_atlas_dimensions
        )
        prepared = prepare_textures(
            None if base is None else base,  # type: ignore[arg-type]
            kind=kind,
            dimensions=atlas_dimensions,
            pixels_per_unit=density,
            texture_mode=mode,
            normal_map=maps[0],
            roughness_map=maps[1],
            metallic_map=maps[2],
            emissive_map=maps[3],
            ambient_occlusion_map=maps[4],
        )
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_texture(
            self._entity._handle,
            None if prepared.texture is None else str(prepared.texture),
            density,
            filtering,
            prepared.mode,
            None if prepared.normal_map is None else str(prepared.normal_map),
            None if prepared.roughness_map is None else str(prepared.roughness_map),
            None if prepared.metallic_map is None else str(prepared.metallic_map),
            None if prepared.emissive_map is None else str(prepared.emissive_map),
            None
            if prepared.ambient_occlusion_map is None
            else str(prepared.ambient_occlusion_map),
            strength,
            reload_enabled,
            atlas_dimensions,
        )
        new_maps = (
            prepared.normal_map,
            prepared.roughness_map,
            prepared.metallic_map,
            prepared.emissive_map,
            prepared.ambient_occlusion_map,
        )
        metallic_value = info[4]
        roughness_value = info[5]
        emission_value = info[6]
        if (old_maps[1] is None) != (new_maps[1] is None):
            roughness_value = 1.0 if new_maps[1] is not None else 0.5
        if (old_maps[2] is None) != (new_maps[2] is None):
            metallic_value = 1.0 if new_maps[2] is not None else 0.0
        if (old_maps[3] is None) != (new_maps[3] is None):
            emission_value = 1.0 if new_maps[3] is not None else 0.0
        if (
            metallic_value != info[4]
            or roughness_value != info[5]
            or emission_value != info[6]
        ):
            self._entity.scene._native.set_render_surface(
                self._entity._handle,
                metallic_value,
                roughness_value,
                emission_value,
                info[7],
                info[8],
            )

    @property
    def pixels_per_unit(self) -> float:
        return self._info()[9]

    @pixels_per_unit.setter
    def pixels_per_unit(self, value: float) -> None:
        self._apply_texture(pixels_per_unit=value)

    @property
    def texture_filter(self) -> TextureFilter:
        return self._info()[10]  # type: ignore[return-value]

    @texture_filter.setter
    def texture_filter(self, value: TextureFilter) -> None:
        self._apply_texture(texture_filter=value)

    @property
    def texture_mode(self) -> TextureMode:
        return self._info()[11]  # type: ignore[return-value]

    @texture_mode.setter
    def texture_mode(self, value: TextureMode) -> None:
        self._apply_texture(texture_mode=value)

    @property
    def normal_strength(self) -> float:
        return self._info()[12]

    @normal_strength.setter
    def normal_strength(self, value: float) -> None:
        self._apply_texture(normal_strength=value)

    @property
    def normal_map(self) -> Path | None:
        return self._map_path(14)

    @normal_map.setter
    def normal_map(self, value: OptionalMap) -> None:
        self._apply_texture(normal_map=value)

    @property
    def roughness_map(self) -> Path | None:
        return self._map_path(15)

    @roughness_map.setter
    def roughness_map(self, value: OptionalMap) -> None:
        self._apply_texture(roughness_map=value)

    @property
    def metallic_map(self) -> Path | None:
        return self._map_path(16)

    @metallic_map.setter
    def metallic_map(self, value: OptionalMap) -> None:
        self._apply_texture(metallic_map=value)

    @property
    def emissive_map(self) -> Path | None:
        return self._map_path(17)

    @emissive_map.setter
    def emissive_map(self, value: OptionalMap) -> None:
        self._apply_texture(emissive_map=value)

    @property
    def ambient_occlusion_map(self) -> Path | None:
        return self._map_path(18)

    @ambient_occlusion_map.setter
    def ambient_occlusion_map(self, value: OptionalMap) -> None:
        self._apply_texture(ambient_occlusion_map=value)

    @property
    def lit(self) -> bool:
        return self._info()[3]

    @lit.setter
    def lit(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("lit must be a bool")
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_lit(self._entity._handle, value)

    @property
    def cull_mode(self) -> CullMode:
        return self._info()[20]  # type: ignore[return-value]

    @cull_mode.setter
    def cull_mode(self, value: CullMode) -> None:
        mode = validate_cull_mode(value)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_render_cull_mode(self._entity._handle, mode)

    @property
    def double_sided(self) -> bool:
        return self.cull_mode == "none"

    @double_sided.setter
    def double_sided(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("double_sided must be a bool")
        self.cull_mode = "none" if value else "back"

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

    def _info(
        self,
    ) -> tuple[
        str,
        tuple[float, float, float, float],
        float,
        float,
        float,
        float,
        bool,
        int,
        float,
    ]:
        info = self._entity.scene._native.light_component_info(self._entity._handle)
        return (info[0], tuple(info[1]), *info[2:])

    def _set_properties(
        self,
        *,
        range: float | None = None,
        inner_angle: float | None = None,
        outer_angle: float | None = None,
        casts_shadows: bool | None = None,
        shadow_resolution: int | None = None,
        shadow_bias: float | None = None,
    ) -> None:
        info = self._info()
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_light_properties(
            self._entity._handle,
            info[3] if range is None else range,
            info[4] if inner_angle is None else inner_angle,
            info[5] if outer_angle is None else outer_angle,
            info[6] if casts_shadows is None else casts_shadows,
            info[7] if shadow_resolution is None else shadow_resolution,
            info[8] if shadow_bias is None else shadow_bias,
        )

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

    @property
    def range(self) -> float:
        return self._info()[3]

    @range.setter
    def range(self, value: float) -> None:
        self._set_properties(range=float(value))

    @property
    def inner_angle(self) -> float:
        return self._info()[4]

    @inner_angle.setter
    def inner_angle(self, value: float) -> None:
        self._set_properties(inner_angle=float(value))

    @property
    def angle(self) -> float:
        return self._info()[5]

    @angle.setter
    def angle(self, value: float) -> None:
        self._set_properties(outer_angle=float(value))

    @property
    def casts_shadows(self) -> bool:
        return self._info()[6]

    @casts_shadows.setter
    def casts_shadows(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("casts_shadows must be a bool")
        self._set_properties(casts_shadows=value)

    @property
    def shadow_resolution(self) -> int:
        return self._info()[7]

    @shadow_resolution.setter
    def shadow_resolution(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("shadow_resolution must be an int")
        self._set_properties(shadow_resolution=value)

    @property
    def shadow_bias(self) -> float:
        return self._info()[8]

    @shadow_bias.setter
    def shadow_bias(self, value: float) -> None:
        self._set_properties(shadow_bias=float(value))

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
            raise TypeError("material must be an rix.PhysicsMaterial")
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
        promote_collider = getattr(entity, "_rix_promote_collider", None)
        if callable(promote_collider):
            promote_collider()
            delattr(entity, "_rix_promote_collider")
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

    @property
    def angular_velocity(self) -> Vec3:
        """World-axis angular velocity in degrees per second."""

        return Vec3(
            self._entity.scene._native.rigid_body_angular_velocity(
                self._entity._handle
            )
        )

    @angular_velocity.setter
    def angular_velocity(self, value: Vec3 | tuple[float, float, float]) -> None:
        velocity = Vec3.from_value(value)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_rigid_body_angular_velocity(
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
        *,
        reset_motion: bool = False,
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
        if reset_motion:
            self._entity.scene._native.reset_entity_motion(self._entity._handle)

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_rigid_body_component(self._entity._handle)


class CharacterController:
    """Native capsule motor with projection-based ground and air movement."""

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
        air_acceleration_value = _finite_non_negative(
            air_acceleration, "air_acceleration"
        )
        ground_friction_value = _finite_non_negative(
            ground_friction, "ground_friction"
        )
        stop_speed_value = _finite_non_negative(stop_speed, "stop_speed")
        air_speed_cap_value = _finite_non_negative(air_speed_cap, "air_speed_cap")
        horizontal_speed_limit_value = (
            0.0
            if horizontal_speed_limit is None
            else _finite_non_negative(horizontal_speed_limit, "horizontal_speed_limit")
        )
        jump_speed_value = _finite_non_negative(jump_speed, "jump_speed")
        slope_value = float(max_slope_degrees)
        if not math.isfinite(slope_value) or not 0 <= slope_value < 90:
            raise ValueError("max_slope_degrees must be finite and in [0, 90)")
        step_value = _finite_non_negative(step_height, "step_height")
        sprint_value = float(sprint_multiplier)
        if not math.isfinite(sprint_value) or sprint_value < 1:
            raise ValueError("sprint_multiplier must be finite and at least 1")
        crouch_height_value = (
            max(2 * radius_value + 0.01, height_value * (2.0 / 3.0))
            if crouch_height is None
            else float(crouch_height)
        )
        if (
            not math.isfinite(crouch_height_value)
            or crouch_height_value <= 2 * radius_value
            or crouch_height_value > height_value
        ):
            raise ValueError(
                "crouch_height must be finite, greater than the character diameter, "
                "and no greater than height"
            )
        crouch_speed_value = float(crouch_speed_multiplier)
        if (
            not math.isfinite(crouch_speed_value)
            or not 0 <= crouch_speed_value <= 1
        ):
            raise ValueError(
                "crouch_speed_multiplier must be finite and between 0 and 1"
            )
        entity.scene._require_mutable()
        entity.scene._native.add_character_controller_component(
            entity._handle,
            mode,
            radius_value,
            height_value,
            speed_value,
            acceleration_value,
            air_acceleration_value,
            ground_friction_value,
            stop_speed_value,
            air_speed_cap_value,
            horizontal_speed_limit_value,
            jump_speed_value,
            slope_value,
            step_value,
            sprint_value,
            crouch_height_value,
            crouch_speed_value,
        )
        self._entity = entity

    @classmethod
    def _existing(cls, entity: Entity) -> CharacterController:
        component = cls.__new__(cls)
        component._entity = entity
        return component

    def _info(
        self,
    ) -> tuple[
        str,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
        float,
    ]:
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
    def air_acceleration(self) -> float:
        return self._info()[5]

    @property
    def ground_friction(self) -> float:
        return self._info()[6]

    @property
    def stop_speed(self) -> float:
        return self._info()[7]

    @property
    def air_speed_cap(self) -> float:
        return self._info()[8]

    @property
    def horizontal_speed_limit(self) -> float | None:
        value = self._info()[9]
        return None if value == 0.0 else value

    @property
    def jump_speed(self) -> float:
        return self._info()[10]

    @property
    def max_slope_degrees(self) -> float:
        return self._info()[11]

    @property
    def step_height(self) -> float:
        return self._info()[12]

    @property
    def sprint_multiplier(self) -> float:
        return self._info()[13]

    @property
    def crouch_height(self) -> float:
        return self._info()[14]

    @property
    def crouch_speed_multiplier(self) -> float:
        return self._info()[15]

    def _state(self) -> tuple[object, object, object, object, bool, bool, bool]:
        return self._entity.scene._native.character_state(self._entity._handle)

    @property
    def linear_velocity(self) -> Vec3:
        return Vec3(self._state()[2])  # type: ignore[arg-type]

    @linear_velocity.setter
    def linear_velocity(self, value: Vec3 | tuple[float, float, float]) -> None:
        velocity = Vec3.from_value(value)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_character_linear_velocity(
            self._entity._handle, tuple(velocity)
        )

    @property
    def ground_normal(self) -> Vec3:
        return Vec3(self._state()[3])  # type: ignore[arg-type]

    @property
    def grounded(self) -> bool:
        return self._state()[4]

    @property
    def crouched(self) -> bool:
        return self._state()[5]

    @property
    def sprinting(self) -> bool:
        return self._state()[6]

    def set_input(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
        sprint: bool = False,
        crouch: bool = False,
    ) -> None:
        """Set fixed-step intent; ``jump=True`` is a one-tick jump pulse."""

        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        if not isinstance(sprint, bool):
            raise TypeError("sprint must be a bool")
        if not isinstance(crouch, bool):
            raise TypeError("crouch must be a bool")
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_character_input(
            self._entity._handle, tuple(value), heading, jump, sprint, crouch
        )

    def set_sequenced_input(
        self,
        sequence: int,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
        sprint: bool = False,
        crouch: bool = False,
    ) -> None:
        """Apply one strictly newer prediction input to the native motor."""

        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise TypeError("sequence must be an integer")
        if sequence < 1 or sequence > (1 << 64) - 1:
            raise ValueError("sequence must be between 1 and 2^64 - 1")
        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        if not isinstance(sprint, bool):
            raise TypeError("sprint must be a bool")
        if not isinstance(crouch, bool):
            raise TypeError("crouch must be a bool")
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.set_character_sequenced_input(
            self._entity._handle,
            sequence,
            tuple(value),
            heading,
            jump,
            sprint,
            crouch,
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
        """Restore an authoritative native motor state for reconciliation."""

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
        sprint: bool = False,
        crouch: bool = False,
        delta_seconds: float,
    ) -> None:
        """Replay one validated tick without advancing the rest of the scene."""

        if not isinstance(jump, bool):
            raise TypeError("jump must be a bool")
        if not isinstance(sprint, bool):
            raise TypeError("sprint must be a bool")
        if not isinstance(crouch, bool):
            raise TypeError("crouch must be a bool")
        heading = float(heading_degrees)
        delta = float(delta_seconds)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        if not math.isfinite(delta) or delta <= 0:
            raise ValueError("delta_seconds must be finite and positive")
        value = Vec3.from_value(movement)
        self._entity.scene._require_mutable()
        self._entity.scene._native.replay_character_input(
            self._entity._handle,
            tuple(value),
            heading,
            jump,
            sprint,
            crouch,
            delta,
        )

    def teleport(
        self,
        position: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        reset_motion: bool = False,
    ) -> None:
        heading = float(heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        value = Vec3.from_value(position)
        self._entity.scene._require_mutable()
        self._entity.scene._native.teleport_character(
            self._entity._handle, tuple(value), heading
        )
        if reset_motion:
            self._entity.scene._native.reset_entity_motion(self._entity._handle)

    def remove(self) -> None:
        self._entity.scene._require_mutable()
        self._entity.scene._native.remove_character_controller_component(
            self._entity._handle
        )
