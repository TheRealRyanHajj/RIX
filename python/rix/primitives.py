"""Beginner-facing renderable entity primitives."""

from __future__ import annotations

import math
from collections.abc import Callable
from os import PathLike
from typing import TYPE_CHECKING, Literal

from .autotexture import (
    OptionalMap,
    PreparedTextures,
    TextureFilter,
    TextureMode,
    prepare_textures,
    prepare_model_textures,
    validate_pixels_per_unit,
    validate_texture_filter,
    validate_texture_mode,
)

from .components import (
    Collider,
    CollisionLayer,
    ColorValue,
    CullMode,
    PhysicsMaterial,
    Rigidbody,
    normalize_color,
    resolve_cull_mode,
)
from .entity import Entity
from .math import Vec3
from .textures import SurfaceTexture, coerce_surface_texture

if TYPE_CHECKING:
    from .scene import Scene
    from .world import World


def _scene_for_world(world: World | None, scene: Scene | None) -> Scene | None:
    if world is None:
        return scene
    from .world import World

    if not isinstance(world, World):
        raise TypeError("world must be a rix.World or None")
    world_scene = world.scene
    if world_scene is None:
        raise RuntimeError("World has no active scene")
    if scene is not None and scene is not world_scene:
        raise ValueError("world and scene must refer to the same scene")
    return world_scene


def _apply_surface_texture(
    entity: Entity,
    texture: SurfaceTexture | None,
    *,
    pixels_per_unit: float,
    texture_filter: TextureFilter,
    texture_mode: TextureMode,
    atlas_dimensions: tuple[float, float, float],
) -> None:
    if texture is None:
        return
    entity.scene._native.set_render_image(
        entity._handle,
        texture._native,
        pixels_per_unit,
        texture_filter,
        texture_mode,
        atlas_dimensions,
    )
    entity.texture = texture  # type: ignore[attr-defined]


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _lit(value: bool) -> bool:
    if not isinstance(value, bool):
        raise TypeError("lit must be a bool")
    return value


def _normal_strength(value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or not 0 <= result <= 8:
        raise ValueError("normal_strength must be finite and in [0, 8]")
    return result


def _surface_value(
    value: float | None,
    name: str,
    *,
    minimum: float,
    maximum: float,
    fallback: float,
) -> float:
    if value is None:
        return fallback
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} must be finite and in [{minimum:g}, {maximum:g}]")
    return result


def _surface_values(
    prepared: PreparedTextures,
    metallic: float | None,
    roughness: float | None,
    emission: float | None,
) -> tuple[float, float, float]:
    # A texture map's neutral scalar multiplier is one. Unmapped channels keep
    # RIX's legacy scalar defaults so adding AutoTexture does not turn every
    # ordinary primitive metallic or emissive.
    return (
        _surface_value(
            metallic,
            "metallic",
            minimum=0,
            maximum=1,
            fallback=1.0 if prepared.metallic_map is not None else 0.0,
        ),
        _surface_value(
            roughness,
            "roughness",
            minimum=0.04,
            maximum=1,
            fallback=1.0 if prepared.roughness_map is not None else 0.5,
        ),
        _surface_value(
            emission,
            "emission",
            minimum=0,
            maximum=100,
            fallback=1.0 if prepared.emissive_map is not None else 0.0,
        ),
    )


def _prepare_primitive_textures(
    entity: Entity,
    texture: str | PathLike[str] | None,
    *,
    kind: Literal["cube", "plane", "sphere"],
    dimensions: tuple[float, float, float],
    pixels_per_unit: float | None,
    texture_filter: TextureFilter | None,
    texture_mode: TextureMode | None,
    normal_map: OptionalMap,
    roughness_map: OptionalMap,
    metallic_map: OptionalMap,
    emissive_map: OptionalMap,
    ambient_occlusion_map: OptionalMap,
    normal_strength: float,
    hot_reload: bool | None,
) -> tuple[
    PreparedTextures,
    float,
    TextureFilter,
    float,
    bool,
    tuple[float, float, float],
]:
    density = validate_pixels_per_unit(
        entity.scene._pixels_per_unit if pixels_per_unit is None else pixels_per_unit
    )
    filtering = validate_texture_filter(
        entity.scene._texture_filter if texture_filter is None else texture_filter
    )
    mapping = validate_texture_mode(
        entity.scene._texture_mode if texture_mode is None else texture_mode
    )
    reload_enabled = entity.scene._texture_hot_reload if hot_reload is None else hot_reload
    if not isinstance(reload_enabled, bool):
        raise TypeError("texture_hot_reload must be a bool")
    strength = _normal_strength(normal_strength)
    inherited_scale = entity.world_scale
    mapping_dimensions = (
        abs(dimensions[0] * inherited_scale.x),
        abs(dimensions[1] * inherited_scale.y),
        abs(dimensions[2] * inherited_scale.z),
    )
    prepared = prepare_textures(
        texture,
        kind=kind,
        dimensions=mapping_dimensions,
        pixels_per_unit=density,
        texture_mode=mapping,
        normal_map=normal_map,
        roughness_map=roughness_map,
        metallic_map=metallic_map,
        emissive_map=emissive_map,
        ambient_occlusion_map=ambient_occlusion_map,
    )
    return (
        prepared,
        density,
        filtering,
        strength,
        reload_enabled,
        mapping_dimensions,
    )


def _finish_transform(
    entity: Entity,
    position: Vec3 | tuple[float, float, float],
    rotation: Vec3 | tuple[float, float, float],
    scale: Vec3 | tuple[float, float, float],
) -> None:
    entity.position = position
    entity.rotation = rotation
    entity.scale = scale


def _position(
    value: Vec3 | tuple[float, float, float] | None,
    x: float | None,
    y: float | None,
    z: float | None,
) -> Vec3:
    if value is not None and any(item is not None for item in (x, y, z)):
        raise ValueError("position cannot be combined with x, y, or z")
    return Vec3.from_value(
        value
        if value is not None
        else (0.0 if x is None else x, 0.0 if y is None else y, 0.0 if z is None else z)
    )


def _rotation(
    value: Vec3 | tuple[float, float, float] | None,
    rx: float | None,
    ry: float | None,
    rz: float | None,
) -> Vec3:
    if value is not None and any(item is not None for item in (rx, ry, rz)):
        raise ValueError("rotation cannot be combined with rx, ry, or rz")
    return Vec3.from_value(
        value
        if value is not None
        else (
            0.0 if rx is None else rx,
            0.0 if ry is None else ry,
            0.0 if rz is None else rz,
        )
    )


def _finish_physics(
    entity: Entity,
    add_collider: Callable[[bool, CollisionLayer, PhysicsMaterial], None],
    *,
    collider: bool,
    physics: bool,
    mass: float | None,
    trigger: bool | Callable[[object], None],
    gravity: bool,
    friction: float,
    bounciness: float,
    collision_layer: CollisionLayer | None,
    continuous: bool,
    kinematic: bool,
) -> None:
    if not isinstance(collider, bool) or not isinstance(physics, bool):
        raise TypeError("collider and physics must be bools")
    if not isinstance(trigger, bool) and not callable(trigger):
        raise TypeError("trigger must be a bool or callback")
    if trigger and physics:
        raise ValueError("trigger sensors cannot also use dynamic physics")
    if mass is not None and not physics:
        raise ValueError("mass requires physics=True")
    if not isinstance(gravity, bool):
        raise TypeError("gravity must be a bool")
    if not isinstance(continuous, bool) or not isinstance(kinematic, bool):
        raise TypeError("continuous and kinematic must be bools")
    if not physics and (not gravity or continuous or kinematic):
        raise ValueError("gravity, continuous, and kinematic require physics=True")
    if continuous and kinematic:
        raise ValueError("continuous collision detection requires a dynamic body")
    has_motion = any(
        vector.length > 1.0e-12
        for vector in (
            entity.velocity,
            entity.acceleration,
            entity.angular_velocity,
            entity.angular_acceleration,
        )
    )
    if has_motion and (collider or trigger) and not physics:
        raise ValueError(
            "moving collider-only entities require physics=True with a "
            "kinematic Rigidbody (kinematic=True) for scripted motion"
        )
    wants_trigger = bool(trigger)
    layer = collision_layer or (
        "sensor" if wants_trigger else "dynamic" if physics else "static"
    )
    if wants_trigger and layer != "sensor":
        raise ValueError("trigger sensors require collision_layer='sensor'")
    if physics and layer != "dynamic":
        raise ValueError("dynamic and kinematic bodies require collision_layer='dynamic'")
    material = PhysicsMaterial(friction=friction, restitution=bounciness)
    transferred_motion = None
    if physics and has_motion:
        transferred_motion = (
            Vec3(entity.velocity),
            Vec3(entity.acceleration),
            Vec3(entity.angular_velocity),
            Vec3(entity.angular_acceleration),
        )
        entity.scene._native.reset_entity_motion(entity._handle)
    if collider or physics or wants_trigger:
        add_collider(wants_trigger, layer, material)
    if collider and not physics and not wants_trigger and collision_layer is None:
        # The convenience contract makes a collider-only primitive static, but
        # older RIX code commonly attached a Rigidbody in a second step.
        # Preserve that workflow by allowing Rigidbody to promote only this
        # implicit static collider to the dynamic layer.
        def promote_collider() -> None:
            existing = entity.get_component(Collider)
            if existing is not None:
                existing.remove()
            add_collider(False, "dynamic", material)

        entity._rix_promote_collider = promote_collider  # type: ignore[attr-defined]
    if physics:
        entity.add_component(
            Rigidbody,
            body_type="kinematic" if kinematic else "dynamic",
            mass=1.0 if mass is None else mass,
            use_gravity=gravity,
            continuous=continuous,
        )
        if transferred_motion is not None:
            (
                entity.velocity,
                entity.acceleration,
                entity.angular_velocity,
                entity.angular_acceleration,
            ) = transferred_motion
    if callable(trigger):
        entity.on_trigger_enter = trigger  # type: ignore[attr-defined]
        entity.scene._register_script_entity(entity)


class Cube(Entity):
    def __init__(
        self,
        world: World | None = None,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        rotation: Vec3 | tuple[float, float, float] | None = None,
        size: float | tuple[float, float, float] = 1.0,
        scale: float | tuple[float, float, float] | Vec3 | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        rx: float | None = None,
        ry: float | None = None,
        rz: float | None = None,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | SurfaceTexture | object | None = None,
        pixels_per_unit: float | None = None,
        texture_filter: TextureFilter | None = None,
        texture_mode: TextureMode | None = None,
        normal_map: OptionalMap = None,
        roughness_map: OptionalMap = None,
        metallic_map: OptionalMap = None,
        emissive_map: OptionalMap = None,
        ambient_occlusion_map: OptionalMap = None,
        normal_strength: float = 1.0,
        metallic: float | None = None,
        roughness: float | None = None,
        emission: float | None = None,
        texture_hot_reload: bool | None = None,
        lit: bool = True,
        cull_mode: CullMode | None = None,
        double_sided: bool | None = None,
        collider: bool = True,
        physics: bool = False,
        mass: float | None = None,
        trigger: bool | Callable[[object], None] = False,
        gravity: bool = True,
        friction: float = 0.2,
        bounciness: float = 0.0,
        collision_layer: CollisionLayer | None = None,
        continuous: bool = False,
        kinematic: bool = False,
        name: str = "Cube",
        parent: Entity | None = None,
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        scene = _scene_for_world(world, scene)
        surface_texture = coerce_surface_texture(texture)
        texture_path = None if surface_texture is not None else texture
        if scale is not None and size != 1.0:
            raise ValueError("scale cannot be combined with a non-default size")
        extent_value = size if scale is None else scale
        if isinstance(extent_value, (tuple, Vec3)):
            scale_value = Vec3.from_value(extent_value)
            if min(scale_value.x, scale_value.y, scale_value.z) <= 0:
                raise ValueError("cube size components must be positive")
        else:
            extent = _positive(extent_value, "cube size")
            scale_value = Vec3(extent, extent, extent)
        position_value = _position(position, x, y, z)
        rotation_value = _rotation(rotation, rx, ry, rz)
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        culling = resolve_cull_mode(cull_mode, double_sided)
        super().__init__(
            name,
            parent=parent,
            scene=scene,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        try:
            prepared, density, filtering, strength, hot_reload, atlas_dimensions = (
                _prepare_primitive_textures(
                    self,
                    texture_path,  # type: ignore[arg-type]
                    kind="cube",
                    dimensions=tuple(scale_value),
                    pixels_per_unit=pixels_per_unit,
                    texture_filter=texture_filter,
                    texture_mode=texture_mode,
                    normal_map=normal_map,
                    roughness_map=roughness_map,
                    metallic_map=metallic_map,
                    emissive_map=emissive_map,
                    ambient_occlusion_map=ambient_occlusion_map,
                    normal_strength=normal_strength,
                    hot_reload=texture_hot_reload,
                )
            )
            self.scene._native.add_primitive_renderer(
                self._handle,
                "cube",
                native_color,
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
                hot_reload,
                atlas_dimensions,
                culling,
            )
            _apply_surface_texture(
                self,
                surface_texture,
                pixels_per_unit=density,
                texture_filter=filtering,
                texture_mode=prepared.mode,
                atlas_dimensions=atlas_dimensions,
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            surface = _surface_values(prepared, metallic, roughness, emission)
            self.scene._native.set_render_surface(
                self._handle, *surface, True, True
            )
            _finish_transform(self, position_value, rotation_value, scale_value)

            def add_collider(
                is_trigger: bool,
                layer: CollisionLayer,
                material: PhysicsMaterial,
            ) -> None:
                self.add_component(
                    Collider,
                    shape="box",
                    half_extents=(
                        scale_value.x * 0.5,
                        scale_value.y * 0.5,
                        scale_value.z * 0.5,
                    ),
                    trigger=is_trigger,
                    layer=layer,
                    material=material,
                )

            _finish_physics(
                self,
                add_collider,
                collider=collider,
                physics=physics,
                mass=mass,
                trigger=trigger,
                gravity=gravity,
                friction=friction,
                bounciness=bounciness,
                collision_layer=collision_layer,
                continuous=continuous,
                kinematic=kinematic,
            )
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Plane(Entity):
    def __init__(
        self,
        world: World | None = None,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        rotation: Vec3 | tuple[float, float, float] | None = None,
        size: float | tuple[float, float] = 1.0,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        rx: float | None = None,
        ry: float | None = None,
        rz: float | None = None,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | SurfaceTexture | object | None = None,
        pixels_per_unit: float | None = None,
        texture_filter: TextureFilter | None = None,
        texture_mode: TextureMode | None = None,
        normal_map: OptionalMap = None,
        roughness_map: OptionalMap = None,
        metallic_map: OptionalMap = None,
        emissive_map: OptionalMap = None,
        ambient_occlusion_map: OptionalMap = None,
        normal_strength: float = 1.0,
        metallic: float | None = None,
        roughness: float | None = None,
        emission: float | None = None,
        texture_hot_reload: bool | None = None,
        lit: bool = True,
        cull_mode: CullMode | None = None,
        double_sided: bool | None = None,
        collider: bool = True,
        friction: float = 0.2,
        bounciness: float = 0.0,
        collision_layer: CollisionLayer | None = None,
        name: str = "Plane",
        parent: Entity | None = None,
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        scene = _scene_for_world(world, scene)
        surface_texture = coerce_surface_texture(texture)
        texture_path = None if surface_texture is not None else texture
        if isinstance(size, tuple):
            if len(size) != 2:
                raise TypeError("plane size must be a number or (width, depth)")
            width = _positive(size[0], "plane width")
            depth = _positive(size[1], "plane depth")
        else:
            width = depth = _positive(size, "plane size")
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        culling = resolve_cull_mode(cull_mode, double_sided)
        position_value = _position(position, x, y, z)
        rotation_value = _rotation(rotation, rx, ry, rz)
        material = PhysicsMaterial(friction=friction, restitution=bounciness)
        if collision_layer is not None and collision_layer not in (
            "static",
            "dynamic",
            "sensor",
            "character",
        ):
            raise ValueError(
                "collision_layer must be static, dynamic, sensor, or character"
            )
        if not isinstance(collider, bool):
            raise TypeError("collider must be a bool")
        super().__init__(
            name,
            parent=parent,
            scene=scene,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        try:
            prepared, density, filtering, strength, hot_reload, atlas_dimensions = (
                _prepare_primitive_textures(
                    self,
                    texture_path,  # type: ignore[arg-type]
                    kind="plane",
                    dimensions=(width, 1.0, depth),
                    pixels_per_unit=pixels_per_unit,
                    texture_filter=texture_filter,
                    texture_mode=texture_mode,
                    normal_map=normal_map,
                    roughness_map=roughness_map,
                    metallic_map=metallic_map,
                    emissive_map=emissive_map,
                    ambient_occlusion_map=ambient_occlusion_map,
                    normal_strength=normal_strength,
                    hot_reload=texture_hot_reload,
                )
            )
            self.scene._native.add_primitive_renderer(
                self._handle,
                "plane",
                native_color,
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
                hot_reload,
                atlas_dimensions,
                culling,
            )
            _apply_surface_texture(
                self,
                surface_texture,
                pixels_per_unit=density,
                texture_filter=filtering,
                texture_mode=prepared.mode,
                atlas_dimensions=atlas_dimensions,
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            surface = _surface_values(prepared, metallic, roughness, emission)
            self.scene._native.set_render_surface(
                self._handle, *surface, True, True
            )
            _finish_transform(self, position_value, rotation_value, (width, 1.0, depth))
            if collider:
                if any(
                    vector.length > 1.0e-12
                    for vector in (
                        self.velocity,
                        self.acceleration,
                        self.angular_velocity,
                        self.angular_acceleration,
                    )
                ):
                    raise ValueError(
                        "moving collider-only entities require a kinematic Rigidbody"
                    )
                layer: CollisionLayer = collision_layer or "static"
                self.add_component(
                    Collider,
                    shape="box",
                    half_extents=(width * 0.5, 0.05, depth * 0.5),
                    layer=layer,
                    material=material,
                )
                if collision_layer is None:
                    def promote_collider() -> None:
                        existing = self.get_component(Collider)
                        if existing is not None:
                            existing.remove()
                        self.add_component(
                            Collider,
                            shape="box",
                            half_extents=(width * 0.5, 0.05, depth * 0.5),
                            layer="dynamic",
                            material=material,
                        )

                    self._rix_promote_collider = promote_collider  # type: ignore[attr-defined]
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Sphere(Entity):
    def __init__(
        self,
        world: World | None = None,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        rotation: Vec3 | tuple[float, float, float] | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        rx: float | None = None,
        ry: float | None = None,
        rz: float | None = None,
        radius: float = 0.5,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | SurfaceTexture | object | None = None,
        pixels_per_unit: float | None = None,
        texture_filter: TextureFilter | None = None,
        texture_mode: TextureMode | None = None,
        normal_map: OptionalMap = None,
        roughness_map: OptionalMap = None,
        metallic_map: OptionalMap = None,
        emissive_map: OptionalMap = None,
        ambient_occlusion_map: OptionalMap = None,
        normal_strength: float = 1.0,
        metallic: float | None = None,
        roughness: float | None = None,
        emission: float | None = None,
        texture_hot_reload: bool | None = None,
        lit: bool = True,
        cull_mode: CullMode | None = None,
        double_sided: bool | None = None,
        collider: bool = True,
        physics: bool = False,
        mass: float | None = None,
        trigger: bool | Callable[[object], None] = False,
        gravity: bool = True,
        friction: float = 0.2,
        bounciness: float = 0.0,
        collision_layer: CollisionLayer | None = None,
        continuous: bool = False,
        kinematic: bool = False,
        name: str = "Sphere",
        parent: Entity | None = None,
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        scene = _scene_for_world(world, scene)
        surface_texture = coerce_surface_texture(texture)
        texture_path = None if surface_texture is not None else texture
        radius_value = _positive(radius, "sphere radius")
        diameter = radius_value * 2.0
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        culling = resolve_cull_mode(cull_mode, double_sided)
        position_value = _position(position, x, y, z)
        rotation_value = _rotation(rotation, rx, ry, rz)
        super().__init__(
            name,
            parent=parent,
            scene=scene,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        try:
            prepared, density, filtering, strength, hot_reload, atlas_dimensions = (
                _prepare_primitive_textures(
                    self,
                    texture_path,  # type: ignore[arg-type]
                    kind="sphere",
                    dimensions=(diameter, diameter, diameter),
                    pixels_per_unit=pixels_per_unit,
                    texture_filter=texture_filter,
                    texture_mode=texture_mode,
                    normal_map=normal_map,
                    roughness_map=roughness_map,
                    metallic_map=metallic_map,
                    emissive_map=emissive_map,
                    ambient_occlusion_map=ambient_occlusion_map,
                    normal_strength=normal_strength,
                    hot_reload=texture_hot_reload,
                )
            )
            self.scene._native.add_primitive_renderer(
                self._handle,
                "sphere",
                native_color,
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
                hot_reload,
                atlas_dimensions,
                culling,
            )
            _apply_surface_texture(
                self,
                surface_texture,
                pixels_per_unit=density,
                texture_filter=filtering,
                texture_mode=prepared.mode,
                atlas_dimensions=atlas_dimensions,
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            surface = _surface_values(prepared, metallic, roughness, emission)
            self.scene._native.set_render_surface(
                self._handle, *surface, True, True
            )
            _finish_transform(
                self,
                position_value,
                rotation_value,
                (diameter, diameter, diameter),
            )

            def add_collider(
                is_trigger: bool,
                layer: CollisionLayer,
                material: PhysicsMaterial,
            ) -> None:
                self.add_component(
                    Collider,
                    shape="sphere",
                    radius=radius_value,
                    trigger=is_trigger,
                    layer=layer,
                    material=material,
                )

            _finish_physics(
                self,
                add_collider,
                collider=collider,
                physics=physics,
                mass=mass,
                trigger=trigger,
                gravity=gravity,
                friction=friction,
                bounciness=bounciness,
                collision_layer=collision_layer,
                continuous=continuous,
                kinematic=kinematic,
            )
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Model(Entity):
    def __init__(
        self,
        world: World | str | PathLike[str] | None = None,
        path: str | PathLike[str] | None = None,
        *,
        position: Vec3 | tuple[float, float, float] | None = None,
        rotation: Vec3 | tuple[float, float, float] | None = None,
        scale: float | Vec3 | tuple[float, float, float] = (1, 1, 1),
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        rx: float | None = None,
        ry: float | None = None,
        rz: float | None = None,
        color: ColorValue = (1, 1, 1, 1),
        lit: bool = True,
        cull_mode: CullMode | None = None,
        double_sided: bool | None = None,
        collider: Literal["mesh", "convex"] | bool = True,
        name: str = "Model",
        parent: Entity | None = None,
        scene: Scene | None = None,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        from .world import World

        if isinstance(world, World):
            if path is None:
                raise TypeError("Model(world, path) requires an asset path")
            scene = _scene_for_world(world, scene)
            asset_path = path
        else:
            if world is not None and path is not None:
                raise TypeError("provide a model path once")
            asset_path = world if world is not None else path
            if asset_path is None:
                raise TypeError("Model requires an asset path")
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        culling_override = (
            None
            if cull_mode is None and double_sided is None
            else resolve_cull_mode(cull_mode, double_sided)
        )
        position_value = _position(position, x, y, z)
        rotation_value = _rotation(rotation, rx, ry, rz)
        scale_value = (
            Vec3(float(scale), float(scale), float(scale))
            if isinstance(scale, (int, float)) and not isinstance(scale, bool)
            else Vec3.from_value(scale)
        )
        if min(scale_value.x, scale_value.y, scale_value.z) <= 0:
            raise ValueError("model scale components must be positive")
        if collider is True:
            collider = "mesh"
        if collider not in (False, "mesh", "convex"):
            raise ValueError("model collider must be False, True, 'mesh', or 'convex'")
        super().__init__(
            name,
            parent=parent,
            scene=scene,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        self._animation_callback: Callable[[Model], None] | None = None
        self._animation_completion_seen = 0
        try:
            prepare_model_textures(asset_path)
            self.scene._native.add_model_renderer(
                self._handle, str(asset_path), native_color, culling_override
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            _finish_transform(self, position_value, rotation_value, scale_value)
            if collider:
                if any(
                    vector.length > 1.0e-12
                    for vector in (
                        self.velocity,
                        self.acceleration,
                        self.angular_velocity,
                        self.angular_acceleration,
                    )
                ):
                    raise ValueError(
                        "moving collider-only entities require a kinematic Rigidbody"
                    )
                self.add_component(Collider, shape=collider, mesh=asset_path)
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise

    def add_animation(
        self, name: str, path: str | PathLike[str]
    ) -> Model:
        """Attach and retarget the first compatible clip from an FBX/glTF file."""

        if not isinstance(name, str) or not name:
            raise ValueError("animation name must be a non-empty string")
        self.scene._native.add_model_animation(self._handle, name, str(path))
        return self

    def play(
        self,
        name: str,
        *,
        loop: bool = True,
        speed: float = 1.0,
        blend: float = 0.0,
        root_motion: bool = False,
        on_complete: Callable[[Model], None] | None = None,
    ) -> Model:
        """Play a clip automatically on the native fixed-step scheduler."""

        if not isinstance(loop, bool) or not isinstance(root_motion, bool):
            raise TypeError("loop and root_motion must be bool values")
        if on_complete is not None and not callable(on_complete):
            raise TypeError("on_complete must be callable or None")
        self.scene._native.play_model_animation(
            self._handle, name, loop, float(speed), float(blend), root_motion
        )
        self._animation_callback = on_complete
        self._animation_completion_seen = self._animation_info()[-1]
        return self

    def pause_animation(self) -> Model:
        self.scene._native.pause_model_animation(self._handle)
        return self

    def resume_animation(self) -> Model:
        self.scene._native.resume_model_animation(self._handle)
        return self

    def stop_animation(self) -> Model:
        self.scene._native.stop_model_animation(self._handle)
        self._animation_callback = None
        return self

    def _animation_info(
        self,
    ) -> tuple[
        list[tuple[str, float]],
        str,
        float,
        float,
        float,
        bool,
        bool,
        bool,
        bool,
        Literal["gpu", "cpu"],
        int,
    ]:
        return self.scene._native.model_animation_info(self._handle)

    @property
    def animation_clips(self) -> tuple[str, ...]:
        """Names of embedded and externally attached skeletal clips."""

        return tuple(name for name, _duration in self._animation_info()[0])

    @property
    def current_animation(self) -> str | None:
        value = self._animation_info()[1]
        return value or None

    @property
    def animation_time(self) -> float:
        return self._animation_info()[2]

    @property
    def animation_duration(self) -> float:
        return self._animation_info()[3]

    @property
    def animation_speed(self) -> float:
        return self._animation_info()[4]

    @property
    def animation_state(self) -> Literal["stopped", "playing", "paused"]:
        info = self._animation_info()
        if not info[6]:
            return "stopped"
        return "paused" if info[7] else "playing"

    @property
    def animation_skinning(self) -> Literal["gpu", "cpu"]:
        """Native deformation path selected for this model's joint count."""

        return self._animation_info()[-2]

    def late_update(self, _dt: float) -> None:
        callback = self._animation_callback
        if callback is None or not self.is_alive:
            return
        completion = self._animation_info()[-1]
        if completion == self._animation_completion_seen:
            return
        self._animation_completion_seen = completion
        self._animation_callback = None
        callback(self)
