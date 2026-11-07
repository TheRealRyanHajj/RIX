"""Runtime texture bridges, including explicit Pygame Surface uploads."""

from __future__ import annotations

from os import PathLike
from typing import Any

from ._rix import _DynamicImage


def _pygame() -> Any:
    try:
        import pygame
    except ImportError as error:
        raise ImportError(
            "Pygame Surface textures require pygame-ce; install rix[pygame]"
        ) from error
    return pygame


class SurfaceTexture:
    """Owned RGBA8 copy of a Pygame Surface used by RIX on the GPU.

    Construction and :meth:`update` copy pixels immediately, so the source
    Surface may be modified or released without leaving dangling native memory.
    Updates are explicit; RIX never scans or uploads a Surface every frame.
    """

    __slots__ = ("_native", "_size", "_srgb")

    def __init__(self, surface: object, *, srgb: bool = True) -> None:
        if not isinstance(srgb, bool):
            raise TypeError("srgb must be a bool")
        pygame = _pygame()
        if not isinstance(surface, pygame.Surface):
            raise TypeError("surface must be a pygame.Surface")
        width, height = surface.get_size()
        if width <= 0 or height <= 0:
            raise ValueError("surface dimensions must be positive")
        rgba8 = pygame.image.tobytes(surface, "RGBA", False)
        self._native = _DynamicImage(width, height, rgba8, srgb)
        self._size = (width, height)
        self._srgb = srgb

    @property
    def size(self) -> tuple[int, int]:
        return self._size

    @property
    def width(self) -> int:
        return self._size[0]

    @property
    def height(self) -> int:
        return self._size[1]

    @property
    def srgb(self) -> bool:
        return self._srgb

    @property
    def revision(self) -> int:
        return int(self._native.revision)

    def update(self, surface: object) -> None:
        """Copy current pixels from a Surface and refresh the GPU next render."""

        pygame = _pygame()
        if not isinstance(surface, pygame.Surface):
            raise TypeError("surface must be a pygame.Surface")
        width, height = surface.get_size()
        if width <= 0 or height <= 0:
            raise ValueError("surface dimensions must be positive")
        rgba8 = pygame.image.tobytes(surface, "RGBA", False)
        self._native.update(width, height, rgba8)
        self._size = (width, height)


def coerce_surface_texture(value: object) -> SurfaceTexture | None:
    if isinstance(value, SurfaceTexture):
        return value
    if value is None or isinstance(value, (str, bytes, PathLike)):
        return None
    try:
        pygame = _pygame()
    except ImportError:
        return None
    if isinstance(value, pygame.Surface):
        return SurfaceTexture(value)
    return None

