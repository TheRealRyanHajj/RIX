"""Scene-owned procedural, panoramic, and cubemap skies."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias
import weakref

from .autotexture import _png_bytes, _write_new
from .components import ColorValue, normalize_color

if TYPE_CHECKING:
    from .scene import Scene

SkyboxKind: TypeAlias = Literal["procedural", "panorama", "cubemap"]
CubemapSource: TypeAlias = str | Path | Mapping[str, str | Path]

_FACE_NAMES = ("right", "left", "top", "bottom", "back", "front")


def _write_metadata(path: Path, kind: str, size: tuple[int, int]) -> None:
    sidecar = path.with_suffix(path.suffix + ".skybox.json")
    data = {
        "generator": "rix-skybox-v1",
        "kind": kind,
        "width": size[0],
        "height": size[1],
    }
    try:
        with sidecar.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except FileExistsError:
        pass


def _generate_panorama(path: Path) -> None:
    if path.exists():
        return
    width, height = 2048, 1024
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = bytearray(width * height * 4)
    for y in range(height):
        t = y / (height - 1)
        if t < 0.5:
            blend = t * 2.0
            first, second = (55, 120, 205), (185, 215, 242)
        else:
            blend = (t - 0.5) * 2.0
            first, second = (185, 215, 242), (30, 38, 58)
        color = tuple(round(a + (b - a) * blend) for a, b in zip(first, second))
        row = bytes((*color, 255)) * width
        start = y * width * 4
        pixels[start : start + width * 4] = row
    _write_new(path, _png_bytes(width, height, bytes(pixels)))
    _write_metadata(path, "panorama", (width, height))


def _generated_sky_color(direction_y: float) -> bytes:
    top = (55, 120, 205)
    horizon = (185, 215, 242)
    bottom = (30, 38, 58)
    amount = min(abs(direction_y), 1.0)
    target = top if direction_y >= 0.0 else bottom
    return bytes((*(round(a + (b - a) * amount) for a, b in zip(horizon, target)), 255))


def _generate_face(path: Path, face: str) -> None:
    if path.exists():
        return
    size = 512
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = bytearray(size * size * 4)
    for y in range(size):
        v = y * 2.0 / (size - 1) - 1.0
        for x in range(size):
            u = x * 2.0 / (size - 1) - 1.0
            denominator = math.sqrt(1.0 + u * u + v * v)
            if face == "top":
                direction_y = 1.0 / denominator
            elif face == "bottom":
                direction_y = -1.0 / denominator
            else:
                direction_y = -v / denominator
            start = (y * size + x) * 4
            pixels[start : start + 4] = _generated_sky_color(direction_y)
    _write_new(path, _png_bytes(size, size, bytes(pixels)))
    _write_metadata(path, "cubemap-face", (size, size))


def _cubemap_paths(
    source: CubemapSource,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    if isinstance(source, Mapping):
        missing = [name for name in _FACE_NAMES if name not in source]
        if missing:
            raise ValueError(f"cubemap mapping is missing faces: {', '.join(missing)}")
        paths = tuple(Path(source[name]) for name in _FACE_NAMES)
    else:
        folder = Path(source)
        paths = tuple(folder / f"{name}.png" for name in _FACE_NAMES)
    for path, face in zip(paths, _FACE_NAMES):
        _generate_face(path, face)
    return (paths[0], paths[1], paths[2], paths[3], paths[4], paths[5])


class Skybox:
    """A mutable sky definition that becomes live when assigned to a scene."""

    def __init__(
        self,
        *,
        top: ColorValue = "skyblue",
        horizon: ColorValue = "lightblue",
        bottom: ColorValue = (0.08, 0.10, 0.16, 1.0),
        brightness: float = 1.0,
        rotation: float = 0.0,
        panorama: str | Path | None = None,
        cubemap: CubemapSource | None = None,
    ) -> None:
        if panorama is not None and cubemap is not None:
            raise ValueError("a skybox cannot use panorama and cubemap sources together")
        self._top = normalize_color(top)
        self._horizon = normalize_color(horizon)
        self._bottom = normalize_color(bottom)
        self._brightness = self._finite(brightness, "brightness", minimum=0.0, maximum=32.0)
        self._rotation = self._finite(rotation, "rotation")
        self._panorama = None if panorama is None else Path(panorama)
        self._cubemap = None if cubemap is None else _cubemap_paths(cubemap)
        if self._panorama is not None:
            _generate_panorama(self._panorama)
        self._scene_ref: weakref.ReferenceType[Scene] | None = None

    @staticmethod
    def _finite(value: float, name: str, *, minimum: float | None = None,
                maximum: float | None = None) -> float:
        result = float(value)
        if not math.isfinite(result) or (minimum is not None and result < minimum) or (
            maximum is not None and result > maximum
        ):
            limits = "finite" if minimum is None else f"in [{minimum}, {maximum}]"
            raise ValueError(f"skybox {name} must be {limits}")
        return result

    @property
    def kind(self) -> SkyboxKind:
        if self._panorama is not None:
            return "panorama"
        if self._cubemap is not None:
            return "cubemap"
        return "procedural"

    def _bound_copy(self, scene: Scene) -> Skybox:
        value = object.__new__(Skybox)
        value._top, value._horizon, value._bottom = self._top, self._horizon, self._bottom
        value._brightness, value._rotation = self._brightness, self._rotation
        value._panorama, value._cubemap = self._panorama, self._cubemap
        value._scene_ref = weakref.ref(scene)
        value._apply()
        return value

    def _apply(self) -> None:
        scene = None if self._scene_ref is None else self._scene_ref()
        if scene is None:
            return
        scene._require_mutable()
        if self._panorama is not None:
            scene._native.set_panorama_skybox(str(self._panorama), self._brightness, self._rotation)
        elif self._cubemap is not None:
            paths = self._cubemap
            scene._native.set_cubemap_skybox(
                (
                    str(paths[0]), str(paths[1]), str(paths[2]),
                    str(paths[3]), str(paths[4]), str(paths[5]),
                ),
                self._brightness,
                self._rotation,
            )
        else:
            scene._native.set_procedural_skybox(
                self._top, self._horizon, self._bottom, self._brightness, self._rotation
            )

    @property
    def top(self) -> tuple[float, float, float, float]:
        return self._top

    @top.setter
    def top(self, value: ColorValue) -> None:
        self._top = normalize_color(value)
        self._apply()

    @property
    def horizon(self) -> tuple[float, float, float, float]:
        return self._horizon

    @horizon.setter
    def horizon(self, value: ColorValue) -> None:
        self._horizon = normalize_color(value)
        self._apply()

    @property
    def bottom(self) -> tuple[float, float, float, float]:
        return self._bottom

    @bottom.setter
    def bottom(self, value: ColorValue) -> None:
        self._bottom = normalize_color(value)
        self._apply()

    @property
    def brightness(self) -> float:
        return self._brightness

    @brightness.setter
    def brightness(self, value: float) -> None:
        self._brightness = self._finite(value, "brightness", minimum=0.0, maximum=32.0)
        self._apply()

    @property
    def rotation(self) -> float:
        return self._rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        self._rotation = self._finite(value, "rotation")
        self._apply()
