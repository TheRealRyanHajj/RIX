"""Texture asset loading and shared CPU image caching."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Literal, TypeAlias

from ._easy3d import _TextureCache, _TextureColorSpace, _load_image_info

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
