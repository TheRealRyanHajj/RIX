"""Camera-independent, buffered Pygame views of a RIX world."""

from __future__ import annotations

from typing import Any

from .camera import Camera
from .world import World, _pygame


def _copy_camera(camera: Camera) -> Camera:
    return Camera(
        position=camera.position,
        rotation=camera.rotation,
        vertical_fov_degrees=camera.vertical_fov_degrees,
        near_plane=camera.near_plane,
        far_plane=camera.far_plane,
        projection=camera.projection,
        orthographic_height=camera.orthographic_height,
    )


class Viewport:
    """Render a world through an independent camera into a cached Surface.

    The first default refresh blocks so a useful image is returned immediately.
    Later default refreshes use a native asynchronous readback request and return
    the newest completed cached frame, normally introducing one frame of latency
    without stalling the application's main presentation path. Pass
    ``blocking=True`` when the newest frame is required immediately.
    """

    __slots__ = ("world", "rect", "camera", "_surface", "_pending", "_closed")

    def __init__(
        self,
        world: World,
        *,
        size: tuple[int, int] | None = None,
        rect: object | None = None,
        camera: Camera | None = None,
    ) -> None:
        if not isinstance(world, World):
            raise TypeError("world must be a rix.World")
        pygame = _pygame()
        if rect is not None and size is not None:
            raise ValueError("size and rect are mutually exclusive")
        if rect is not None:
            try:
                resolved = pygame.Rect(rect)
            except (TypeError, ValueError) as error:
                raise TypeError("rect must be pygame.Rect-compatible") from error
        else:
            selected = world.game._engine.viewport_size if size is None else size
            if (
                not isinstance(selected, tuple)
                or len(selected) != 2
                or any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in selected
                )
            ):
                raise TypeError("size must be a (width, height) tuple of integers")
            resolved = pygame.Rect(0, 0, selected[0], selected[1])
        if resolved.width <= 0 or resolved.height <= 0:
            raise ValueError("viewport dimensions must be positive")
        if camera is not None and not isinstance(camera, Camera):
            raise TypeError("camera must be a rix.Camera or None")
        self.world = world
        self.rect = resolved
        self.camera = _copy_camera(world.camera if camera is None else camera)
        self._surface: Any | None = None
        self._pending: int | None = None
        self._closed = False

    @property
    def size(self) -> tuple[int, int]:
        return self.rect.size

    @property
    def closed(self) -> bool:
        return self._closed

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Viewport is closed")

    def refresh(self, *, blocking: bool | None = None):
        """Refresh and return the cached Surface.

        ``blocking=None`` blocks only for the first image and buffers later
        refreshes. ``False`` always returns promptly (creating a transparent
        placeholder before the first readback). ``True`` waits for fresh pixels.
        """

        self._require_open()
        should_block = self._surface is None if blocking is None else blocking
        if not isinstance(should_block, bool):
            raise TypeError("blocking must be a bool or None")

        completed_pending = False
        if self._pending is not None:
            completed = (
                self.world._wait_viewport(self._pending, self.size)
                if should_block
                else self.world._poll_viewport(self._pending, self.size)
            )
            if completed is not None:
                self._surface = completed
                self._pending = None
                completed_pending = True

        if should_block and self._pending is None and not completed_pending:
            self._surface = self.world._render_viewport(self.camera, self.size)
        elif not should_block and self._pending is None:
            self._pending = self.world._request_viewport(self.camera, self.size)

        if self._surface is None:
            pygame = _pygame()
            self._surface = pygame.Surface(self.size, pygame.SRCALPHA)
        return self._surface

    def to_surface(self, *, refresh: bool = True, blocking: bool | None = None):
        if refresh or self._surface is None:
            return self.refresh(blocking=blocking)
        self._require_open()
        return self._surface

    def close(self) -> None:
        """Cancel any outstanding refresh and release this Viewport handle."""

        if self._closed:
            return
        if self._pending is not None:
            self.world._cancel_viewport(self._pending)
            self._pending = None
        self._closed = True

    def __enter__(self) -> Viewport:
        self._require_open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
