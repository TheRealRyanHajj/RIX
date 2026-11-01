"""Beginner-facing ambient and directional lights."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .components import ColorValue, LightComponent, LightKind, normalize_color
from .entity import Entity
from .math import Vec3

if TYPE_CHECKING:
    from .scene import Scene


class Light(Entity):
    """An ambient or directional light stored in the native scene registry."""

    def __init__(
        self,
        type: LightKind = "directional",
        *,
        color: ColorValue = (1, 1, 1, 1),
        intensity: float = 1.0,
        rotation: Vec3 | tuple[float, float, float] = (-45, -30, 0),
        name: str | None = None,
        scene: Scene | None = None,
    ) -> None:
        if type not in ("ambient", "directional"):
            raise ValueError("light type must be 'ambient' or 'directional'")
        native_color = normalize_color(color)
        native_intensity = float(intensity)
        if not math.isfinite(native_intensity) or native_intensity < 0:
            raise ValueError("light intensity must be finite and non-negative")
        super().__init__(name or f"{type.title()} Light", scene=scene)
        try:
            self.scene._native.add_light_component(
                self._handle, type, native_color, native_intensity
            )
            self.rotation = rotation
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
