"""Persistent native debug-drawing helpers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .components import ColorValue
from .math import Vec3

if TYPE_CHECKING:
    from .scene import Scene


def line(
    start: Vec3 | tuple[float, float, float],
    end: Vec3 | tuple[float, float, float],
    *,
    color: ColorValue = (1, 1, 1, 1),
    depth_test: bool = True,
    scene: Scene | None = None,
) -> None:
    """Add a persistent native line to ``scene`` until debug lines are cleared."""

    from .scene import Scene

    owner = scene if scene is not None else Scene.current()
    if not isinstance(owner, Scene):
        raise TypeError("scene must be an easy3d.Scene")
    owner.add_debug_line(start, end, color=color, depth_test=depth_test)


def axes(
    origin: Vec3 | tuple[float, float, float] = (0, 0, 0),
    *,
    size: float = 1.0,
    depth_test: bool = True,
    scene: Scene | None = None,
) -> None:
    """Draw RGB +X/+Y/+Z axes with persistent native lines."""

    length = float(size)
    if not math.isfinite(length) or length <= 0:
        raise ValueError("axis size must be finite and positive")
    start = Vec3.from_value(origin)
    line(start, start + Vec3(length, 0, 0), color=(1, 0.2, 0.2),
         depth_test=depth_test, scene=scene)
    line(start, start + Vec3(0, length, 0), color=(0.2, 1, 0.2),
         depth_test=depth_test, scene=scene)
    line(start, start + Vec3(0, 0, length), color=(0.2, 0.4, 1),
         depth_test=depth_test, scene=scene)
