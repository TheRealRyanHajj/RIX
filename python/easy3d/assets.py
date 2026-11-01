"""Texture asset loading and shared CPU image caching."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Literal, TypeAlias

from ._easy3d import (
    _ModelCache,
    _TextureCache,
    _TextureColorSpace,
    _load_image_info,
    _load_obj_info,
)

ColorSpace: TypeAlias = Literal["srgb", "linear"]


def _native_color_space(value: ColorSpace) -> _TextureColorSpace:
    if value == "srgb":
        return _TextureColorSpace.SRGB
    if value == "linear":
        return _TextureColorSpace.LINEAR
    raise ValueError("color_space must be 'srgb' or 'linear'")


@dataclass(frozen=True, slots=True)
class ImageInfo:
    """Immutable metadata for a native RGBA8 image resource."""

    path: Path
    width: int
    height: int
    byte_size: int
    color_space: ColorSpace


def _to_info(value: tuple[str, int, int, int, bool]) -> ImageInfo:
    path, width, height, byte_size, is_srgb = value
    return ImageInfo(
        Path(path), width, height, byte_size, "srgb" if is_srgb else "linear"
    )


def load_image(
    path: str | PathLike[str], *, color_space: ColorSpace = "srgb"
) -> ImageInfo:
    """Decode a PNG/JPEG to native RGBA8 storage and return its metadata."""

    return _to_info(_load_image_info(str(path), _native_color_space(color_space)))


class TextureCache:
    """Thread-safe cache keyed by canonical path and color space."""

    __slots__ = ("_native",)

    def __init__(self) -> None:
        self._native = _TextureCache()

    def load(
        self, path: str | PathLike[str], *, color_space: ColorSpace = "srgb"
    ) -> ImageInfo:
        return _to_info(
            self._native.load(str(path), _native_color_space(color_space))
        )

    def clear(self) -> None:
        self._native.clear()

    def __len__(self) -> int:
        return self._native.size


@dataclass(frozen=True, slots=True)
class ModelMaterialInfo:
    name: str
    diffuse_color: tuple[float, float, float, float]
    diffuse_texture: Path | None


@dataclass(frozen=True, slots=True)
class ModelPartInfo:
    name: str
    vertex_count: int
    index_count: int
    triangle_count: int
    material_index: int


@dataclass(frozen=True, slots=True)
class ModelInfo:
    path: Path
    triangle_count: int
    parts: tuple[ModelPartInfo, ...]
    materials: tuple[ModelMaterialInfo, ...]
    warnings: tuple[str, ...]


def _to_model_info(
    value: tuple[
        str,
        int,
        list[tuple[str, int, int, int, int]],
        list[tuple[str, tuple[float, float, float, float], str | None]],
        list[str],
    ],
) -> ModelInfo:
    path, triangle_count, native_parts, native_materials, warnings = value
    return ModelInfo(
        path=Path(path),
        triangle_count=triangle_count,
        parts=tuple(ModelPartInfo(*part) for part in native_parts),
        materials=tuple(
            ModelMaterialInfo(name, color, Path(texture) if texture else None)
            for name, color, texture in native_materials
        ),
        warnings=tuple(warnings),
    )


def load_obj(path: str | PathLike[str]) -> ModelInfo:
    """Load and triangulate an OBJ/MTL asset into a shared native model."""

    return _to_model_info(_load_obj_info(str(path)))


class ModelCache:
    """Thread-safe immutable OBJ model cache keyed by canonical path."""

    __slots__ = ("_native",)

    def __init__(self) -> None:
        self._native = _ModelCache()

    def load(self, path: str | PathLike[str]) -> ModelInfo:
        return _to_model_info(self._native.load(str(path)))

    def clear(self) -> None:
        self._native.clear()

    def __len__(self) -> int:
        return self._native.size
