"""Friendly game, native-window, and active-scene wrapper."""

from __future__ import annotations

import math
from typing import Final

from ._easy3d import Engine
from .scene import Scene


class Game:
    """Own a native Easy3D window and renderer lifecycle.

    ``run`` blocks on the calling thread until the user closes the window or
    another Python thread calls ``stop``.
    """

    _MAX_DIMENSION: Final = 65_535

    def __init__(
        self,
        title: str = "Easy3D",
        resolution: tuple[int, int] = (1280, 720),
        vsync: bool = True,
        fps_limit: float = 0,
    ) -> None:
        if not isinstance(title, str) or not title:
            raise ValueError("title must be a non-empty string")
        if (
            not isinstance(resolution, tuple)
            or len(resolution) != 2
            or isinstance(resolution[0], bool)
            or isinstance(resolution[1], bool)
            or not isinstance(resolution[0], int)
            or not isinstance(resolution[1], int)
        ):
            raise TypeError("resolution must be a (width, height) tuple of integers")
        width, height = resolution
        if not (1 <= width <= self._MAX_DIMENSION and 1 <= height <= self._MAX_DIMENSION):
            raise ValueError("resolution dimensions must be between 1 and 65535")
        if isinstance(fps_limit, bool) or not isinstance(fps_limit, (int, float)):
            raise TypeError("fps_limit must be a number")
        if not math.isfinite(fps_limit) or fps_limit < 0:
            raise ValueError("fps_limit must be zero (unlimited) or positive")

        self._engine = Engine(title, width, height, bool(vsync), float(fps_limit))
        self._scene: Scene | None = None

    @property
    def scene(self) -> Scene | None:
        return self._scene

    @property
    def is_running(self) -> bool:
        return self._engine.is_running

    @property
    def frame_count(self) -> int:
        return self._engine.frame_count

    @property
    def last_frame_seconds(self) -> float:
        return self._engine.last_frame_seconds

    def run(self) -> None:
        """Open the native window and run until close or ``stop``."""

        self._engine.run()

    def stop(self) -> None:
        """Request a running game to stop; safe to call from another thread."""

        self._engine.stop()

    def load_scene(self, scene: Scene) -> None:
        """Make ``scene`` this game's active scene.

        A scene can be loaded by only one game at a time. Replacing a scene
        deactivates it but does not destroy its entities.
        """

        if not isinstance(scene, Scene):
            raise TypeError("scene must be an easy3d.Scene")
        if self.is_running:
            raise RuntimeError("cannot replace the active scene while Game is running")
        if self._scene is scene:
            return
        scene._attach(self)
        self._engine.set_scene(scene._native)
        previous = self._scene
        self._scene = scene
        if previous is not None:
            previous._detach(self)

    def unload_scene(self, *, clear: bool = False) -> Scene | None:
        """Deactivate and return the current scene, optionally clearing it."""

        scene = self._scene
        if scene is None:
            return None
        if self.is_running:
            raise RuntimeError("cannot unload the active scene while Game is running")
        scene._detach(self)
        self._engine.set_scene(None)
        self._scene = None
        if clear:
            scene.clear()
        return scene

