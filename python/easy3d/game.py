"""Friendly game, native-window, and active-scene wrapper."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Final, Literal

from ._easy3d import Engine
from .input import Input
from .scene import Scene
from .scheduler import SchedulerStats, SimulationScheduler


GraphicsPreset = Literal["low", "medium", "high", "ultra"]


@dataclass(frozen=True, slots=True)
class RendererStats:
    """Counters for the most recently completed rendered frame."""

    draw_calls: int = 0
    visible_instances: int = 0
    culled_instances: int = 0
    instanced_draw_calls: int = 0
    ui_draw_calls: int = 0
    ui_elements: int = 0
    enhanced_lighting: bool = False
    shadows: bool = False
    postprocessing: bool = False
    fxaa: bool = False
    shadow_resolution: int = 0


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
        *,
        fixed_hz: float = 60.0,
        max_frame_seconds: float = 0.25,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
        graphics_preset: GraphicsPreset = "medium",
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
        if graphics_preset not in ("low", "medium", "high", "ultra"):
            raise ValueError(
                "graphics_preset must be 'low', 'medium', 'high', or 'ultra'"
            )

        self._engine = Engine(
            title,
            width,
            height,
            bool(vsync),
            float(fps_limit),
            graphics_preset,
        )
        self._input = Input(self._engine.input)
        self._scheduler = SimulationScheduler(
            fixed_hz=fixed_hz,
            max_frame_seconds=max_frame_seconds,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
        )
        self._scene: Scene | None = None
        self._callback_active = False
        self._gameplay_thread_id: int | None = None

    @property
    def scene(self) -> Scene | None:
        return self._scene

    @property
    def input(self) -> Input:
        return self._input

    @property
    def is_running(self) -> bool:
        return self._engine.is_running

    @property
    def frame_count(self) -> int:
        return self._engine.frame_count

    @property
    def last_frame_seconds(self) -> float:
        return self._engine.last_frame_seconds

    @property
    def renderer_stats(self) -> RendererStats:
        """Return an atomic snapshot of the most recently completed frame."""

        return RendererStats(*self._engine.renderer_stats)

    @property
    def graphics_preset(self) -> GraphicsPreset:
        """Requested renderer preset; unsupported runtime features fall back."""

        return self._engine.graphics_preset  # type: ignore[return-value]

    @property
    def scheduler_stats(self) -> SchedulerStats:
        return self._scheduler.stats

    @property
    def script_errors(self) -> tuple[str, ...]:
        return self._scheduler.errors

    def run(self) -> None:
        """Open the native window and run until close or ``stop``."""

        self._scheduler.begin_run()
        self._gameplay_thread_id = threading.get_ident()

        def frame_callback(delta_seconds: float) -> None:
            self._callback_active = True
            try:
                if self._scene is not None:
                    self._scene.hud._advance(
                        self._input.pointer.position,
                        self._input.mouse_button_down("left"),
                        tuple(self._engine.viewport_size),
                    )
                self._scheduler.advance(self._scene, delta_seconds)
            finally:
                self._callback_active = False

        try:
            self._engine.run(frame_callback)
        finally:
            self._callback_active = True
            try:
                if self._scene is not None:
                    self._scene._commit_deferred(self._scheduler.destroy_callback)
            finally:
                self._callback_active = False
                self._gameplay_thread_id = None

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
        if clear:
            scene.clear()
        scene._detach(self)
        self._engine.set_scene(None)
        self._scene = None
        return scene

    def _allows_scene_mutation(self, scene: Scene) -> bool:
        return (
            scene is self._scene
            and self._callback_active
            and self._gameplay_thread_id == threading.get_ident()
        )

    def _on_entity_destroyed(self, entity: object) -> None:
        self._scheduler.forget(entity)  # type: ignore[arg-type]

