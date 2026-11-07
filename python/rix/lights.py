"""Beginner-facing ambient, directional, point, and spot lights."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .components import ColorValue, LightComponent, LightKind, normalize_color
from .entity import Entity
from .math import Vec3

if TYPE_CHECKING:
    from .scene import Scene


class Light(Entity):
    """A live native light stored in the scene registry."""

    def __init__(
        self,
        type: LightKind = "directional",
        *,
        color: ColorValue = (1, 1, 1, 1),
        intensity: float = 1.0,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        rotation: Vec3 | tuple[float, float, float] = (-45, -30, 0),
        range: float = 10.0,
        angle: float = 45.0,
        inner_angle: float = 30.0,
        casts_shadows: bool | None = None,
        shadow_resolution: int = 0,
        shadow_bias: float = 0.002,
        name: str | None = None,
        scene: Scene | None = None,
        _default: bool = False,
        velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_velocity: Vec3 | tuple[float, float, float] = (0, 0, 0),
        angular_acceleration: Vec3 | tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        if type not in ("ambient", "directional", "point", "spot"):
            raise ValueError(
                "light type must be 'ambient', 'directional', 'point', or 'spot'"
            )
        native_color = normalize_color(color)
        native_intensity = float(intensity)
        if not math.isfinite(native_intensity) or native_intensity < 0:
            raise ValueError("light intensity must be finite and non-negative")
        from .scene import Scene

        owner = scene if scene is not None else Scene.current()
        owner._prepare_light(type, is_default=_default)
        super().__init__(
            name or f"{type.title()} Light",
            scene=owner,
            velocity=velocity,
            acceleration=acceleration,
            angular_velocity=angular_velocity,
            angular_acceleration=angular_acceleration,
        )
        try:
            shadowed = type == "directional" if casts_shadows is None else casts_shadows
            if not isinstance(shadowed, bool):
                raise TypeError("casts_shadows must be a bool or None")
            self.scene._native.add_light_component(
                self._handle,
                type,
                native_color,
                native_intensity,
                float(range),
                float(inner_angle),
                float(angle),
                shadowed,
                shadow_resolution,
                float(shadow_bias),
            )
            self.position = position
            self.rotation = rotation
            self.scene._register_light(type, self, is_default=_default)
        except Exception:
            self.destroy()
            raise

    @property
    def component(self) -> LightComponent:
        component = self.get_component(LightComponent)
        if component is None:
            raise RuntimeError("light entity no longer has its LightComponent")
        return component

    @property
    def type(self) -> LightKind:
        return self.component.kind

    @property
    def color(self) -> tuple[float, float, float, float]:
        return self.component.color

    @color.setter
    def color(self, value: ColorValue) -> None:
        self.component.color = value

    @property
    def intensity(self) -> float:
        return self.component.intensity

    @intensity.setter
    def intensity(self, value: float) -> None:
        self.component.intensity = value

    @property
    def range(self) -> float:
        return self.component.range

    @range.setter
    def range(self, value: float) -> None:
        self.component.range = value

    @property
    def angle(self) -> float:
        return self.component.angle

    @angle.setter
    def angle(self, value: float) -> None:
        self.component.angle = value

    @property
    def inner_angle(self) -> float:
        return self.component.inner_angle

    @inner_angle.setter
    def inner_angle(self, value: float) -> None:
        self.component.inner_angle = value

    @property
    def casts_shadows(self) -> bool:
        return self.component.casts_shadows

    @casts_shadows.setter
    def casts_shadows(self, value: bool) -> None:
        self.component.casts_shadows = value

    @property
    def shadow_resolution(self) -> int:
        return self.component.shadow_resolution

    @shadow_resolution.setter
    def shadow_resolution(self, value: int) -> None:
        self.component.shadow_resolution = value

    @property
    def shadow_bias(self) -> float:
        return self.component.shadow_bias

    @shadow_bias.setter
    def shadow_bias(self, value: float) -> None:
        self.component.shadow_bias = value
