"""Beginner-facing renderable entity primitives."""

from __future__ import annotations

import math
from os import PathLike
from typing import TYPE_CHECKING

from .components import Collider, ColorValue, normalize_color
from .entity import Entity
from .math import Vec3

if TYPE_CHECKING:
    from .scene import Scene


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _lit(value: bool) -> bool:
    if not isinstance(value, bool):
        raise TypeError("lit must be a bool")
    return value


def _finish_transform(
    entity: Entity,
    position: Vec3 | tuple[float, float, float],
    rotation: Vec3 | tuple[float, float, float],
    scale: Vec3 | tuple[float, float, float],
) -> None:
    entity.position = position
    entity.rotation = rotation
    entity.scale = scale


class Cube(Entity):
    def __init__(
        self,
        *,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        rotation: Vec3 | tuple[float, float, float] = (0, 0, 0),
        size: float | tuple[float, float, float] = 1.0,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | None = None,
        lit: bool = True,
        collider: bool = False,
        name: str = "Cube",
        scene: Scene | None = None,
    ) -> None:
        if isinstance(size, tuple):
            scale = Vec3.from_value(size)
            if min(scale.x, scale.y, scale.z) <= 0:
                raise ValueError("cube size components must be positive")
        else:
            extent = _positive(size, "cube size")
            scale = Vec3(extent, extent, extent)
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        if not isinstance(collider, bool):
            raise TypeError("collider must be a bool")
        super().__init__(name, scene=scene)
        try:
            self.scene._native.add_primitive_renderer(
                self._handle,
                "cube",
                native_color,
                None if texture is None else str(texture),
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            _finish_transform(self, position, rotation, scale)
            if collider:
                self.add_component(
                    Collider,
                    shape="box",
                    half_extents=(scale.x * 0.5, scale.y * 0.5, scale.z * 0.5),
                )
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Plane(Entity):
    def __init__(
        self,
        *,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        rotation: Vec3 | tuple[float, float, float] = (0, 0, 0),
        size: float | tuple[float, float] = 1.0,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | None = None,
        lit: bool = True,
        collider: bool = False,
        name: str = "Plane",
        scene: Scene | None = None,
    ) -> None:
        if isinstance(size, tuple):
            if len(size) != 2:
                raise TypeError("plane size must be a number or (width, depth)")
            width = _positive(size[0], "plane width")
            depth = _positive(size[1], "plane depth")
        else:
            width = depth = _positive(size, "plane size")
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        if not isinstance(collider, bool):
            raise TypeError("collider must be a bool")
        super().__init__(name, scene=scene)
        try:
            self.scene._native.add_primitive_renderer(
                self._handle,
                "plane",
                native_color,
                None if texture is None else str(texture),
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            _finish_transform(self, position, rotation, (width, 1.0, depth))
            if collider:
                self.add_component(
                    Collider,
                    shape="box",
                    half_extents=(width * 0.5, 0.05, depth * 0.5),
                )
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Sphere(Entity):
    def __init__(
        self,
        *,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        rotation: Vec3 | tuple[float, float, float] = (0, 0, 0),
        radius: float = 0.5,
        color: ColorValue = (1, 1, 1, 1),
        texture: str | PathLike[str] | None = None,
        lit: bool = True,
        collider: bool = False,
        name: str = "Sphere",
        scene: Scene | None = None,
    ) -> None:
        radius_value = _positive(radius, "sphere radius")
        diameter = radius_value * 2.0
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        if not isinstance(collider, bool):
            raise TypeError("collider must be a bool")
        super().__init__(name, scene=scene)
        try:
            self.scene._native.add_primitive_renderer(
                self._handle,
                "sphere",
                native_color,
                None if texture is None else str(texture),
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            _finish_transform(self, position, rotation, (diameter, diameter, diameter))
            if collider:
                self.add_component(Collider, shape="sphere", radius=radius_value)
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise


class Model(Entity):
    def __init__(
        self,
        path: str | PathLike[str],
        *,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        rotation: Vec3 | tuple[float, float, float] = (0, 0, 0),
        scale: Vec3 | tuple[float, float, float] = (1, 1, 1),
        color: ColorValue = (1, 1, 1, 1),
        lit: bool = True,
        name: str = "Model",
        scene: Scene | None = None,
    ) -> None:
        native_color = normalize_color(color)
        native_lit = _lit(lit)
        super().__init__(name, scene=scene)
        try:
            self.scene._native.add_model_renderer(
                self._handle, str(path), native_color
            )
            self.scene._native.set_render_lit(self._handle, native_lit)
            _finish_transform(self, position, rotation, scale)
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise
