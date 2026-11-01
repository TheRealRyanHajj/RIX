"""Native component facades."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from .entity import Entity

ColorValue: TypeAlias = tuple[float, float, float] | tuple[float, float, float, float]
RenderKind: TypeAlias = Literal["cube", "plane", "sphere", "model"]
LightKind: TypeAlias = Literal["ambient", "directional"]


def normalize_color(value: ColorValue) -> tuple[float, float, float, float]:
    if not isinstance(value, tuple) or len(value) not in (3, 4):
        raise TypeError("color must be an (r, g, b) or (r, g, b, a) tuple")
    components = tuple(float(component) for component in value)
    if not all(math.isfinite(component) and 0 <= component <= 1 for component in components):
        raise ValueError("color components must be finite and between 0 and 1")
    if len(components) == 3:
        return components[0], components[1], components[2], 1.0
    return components  # type: ignore[return-value]


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
    ) -> tuple[str, tuple[float, float, float, float], str | None, bool]:
        kind, color, asset, lit = self._entity.scene._native.render_component_info(
            self._entity._handle
        )
        return kind, tuple(color), asset, lit

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
