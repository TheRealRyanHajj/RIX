"""Friendly game, native-window, and active-scene wrapper."""

from __future__ import annotations

import math
import threading
import weakref
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Literal, overload

from ._rix import Engine
from .audio import Audio, AudioSource
from .input import Input
from .scene import Scene
from .autotexture import (
    TextureFilter,
    TextureMode,
    validate_pixels_per_unit,
    validate_texture_filter,
    validate_texture_mode,
)
from .scheduler import SchedulerStats, SimulationScheduler

if TYPE_CHECKING:
    from .components import CollisionLayer
    from .entity import Entity
    from .math import Vec3
    from .physics import PhysicsHit
    from .utilities import StateMachine, Timer, Tween


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
    cpu_frame_ms: float = 0.0
    gpu_frame_ms: float = 0.0
    texture_count: int = 0
    texture_memory_bytes: int = 0
    active_directional_lights: int = 0
    active_point_lights: int = 0
    active_spot_lights: int = 0
    culled_lights: int = 0
    shadow_passes: int = 0
    active_shadow_casters: int = 0
    dropped_shadow_casters: int = 0
    shadow_memory_bytes: int = 0


class Lighting:
    """Simple access to one scene's ambient and directional lights."""

    __slots__ = ("_scene",)

    def __init__(self, scene: Scene) -> None:
        self._scene = scene

    def _get(self, kind: str):
        from .lights import Light

        light = self._scene._light(kind)
        if light is None:
            light = Light(kind, scene=self._scene, _default=True)  # type: ignore[arg-type]
        return light

    @property
    def ambient(self) -> float:
        return float(self._get("ambient").intensity)

    @ambient.setter
    def ambient(self, value: float) -> None:
        self._get("ambient").intensity = value

    @property
    def directional(self) -> float:
        return float(self._get("directional").intensity)

    @directional.setter
    def directional(self, value: float) -> None:
        key = self._get("directional")
        key.intensity = value
        # The beginner default is a two-source key/fill rig. Preserve its
        # contrast ratio when the simple directional intensity proxy changes;
        # user-authored directional lights retain the established first-light
        # behavior because they replace both defaults.
        if key.id in self._scene._default_light_ids:
            for light in self._scene.lights("directional"):
                if light is not key and light.id in self._scene._default_light_ids:
                    light.intensity = float(value) * (0.55 / 0.95)


class CallbackHandle:
    """Idempotent cancellation handle for a Game callback or timer."""

    __slots__ = ("_cancel", "_active")

    def __init__(self, cancel: Callable[[], None]) -> None:
        self._cancel = cancel
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def cancel(self) -> None:
        if self._active:
            self._active = False
            self._cancel()

    def __enter__(self) -> CallbackHandle:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cancel()


@dataclass(slots=True)
class _ScheduledCallback:
    remaining: float
    interval: float | None
    callback: Callable[[], None]
    cancelled: bool = False
    handle: CallbackHandle | None = None


class _GameEventDriver:
    """Scene script adapter for function callbacks registered on Game."""

    def __init__(self, game: Game, scene: Scene) -> None:
        from .entity import Entity

        self._entity = Entity("Game callbacks", scene=scene)
        # The Game owns this adapter. Keeping only a weak reference in the
        # reverse direction prevents an otherwise unreachable Game/default
        # Scene from surviving until cyclic GC happens to run.
        self._game: weakref.ReferenceType[Game] = weakref.ref(game)
        self._entity.fixed_update = self.fixed_update  # type: ignore[attr-defined]
        self._entity.update = self.update  # type: ignore[attr-defined]
        scene._register_script_entity(self._entity)

    def fixed_update(self, dt: float) -> None:
        game = self._game()
        if game is None:
            return
        for callback in tuple(game._fixed_callbacks):
            callback(dt)

    def update(self, dt: float) -> None:
        game = self._game()
        if game is None:
            return
        # Input edges belong to the rendered frame in which the platform
        # observed them. Dispatch them from update so a short key press cannot
        # disappear on a high-refresh frame that happens to run no fixed tick.
        for action, callback in tuple(game._input_callbacks):
            if game.input.pressed(action):
                callback()
        for callback in tuple(game._update_callbacks):
            callback(dt)
        current = game._timers
        game._timers = []
        for timer in current:
            if timer.cancelled:
                continue
            timer.remaining -= dt
            if timer.remaining <= 0.0:
                timer.callback()
                if timer.interval is not None and not timer.cancelled:
                    timer.remaining = timer.interval
                    game._timers.append(timer)
                elif timer.handle is not None:
                    timer.handle._active = False
            else:
                game._timers.append(timer)


class Game:
    """Own a native RIX window and renderer lifecycle.

    ``run`` blocks on the calling thread until the user closes the window or
    another Python thread calls ``stop``.
    """

    _MAX_DIMENSION: Final = 65_535

    def __init__(
        self,
        title: str = "RIX",
        resolution: tuple[int, int] = (1280, 720),
        vsync: bool = True,
        fps_limit: float = 0,
        *,
        fixed_hz: float = 60.0,
        max_frame_seconds: float = 0.25,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
        graphics_preset: GraphicsPreset = "medium",
        auto_setup: bool = True,
        pixels_per_unit: float = 16,
        texture_filter: TextureFilter = "nearest",
        texture_mode: TextureMode = "auto",
        texture_hot_reload: bool = True,
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
        if not isinstance(auto_setup, bool):
            raise TypeError("auto_setup must be a bool")
        density = validate_pixels_per_unit(pixels_per_unit)
        filtering = validate_texture_filter(texture_filter)
        mapping = validate_texture_mode(texture_mode)
        if not isinstance(texture_hot_reload, bool):
            raise TypeError("texture_hot_reload must be a bool")

        self._engine = Engine(
            title,
            width,
            height,
            bool(vsync),
            float(fps_limit),
            graphics_preset,
        )
        self._input = Input(self._engine.input)
        self._audio = Audio(self._engine)
        self._scheduler = SimulationScheduler(
            fixed_hz=fixed_hz,
            max_frame_seconds=max_frame_seconds,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
        )
        self._scene: Scene | None = None
        self._owned_default_scene: Scene | None = None
        self._lighting: Lighting | None = None
        self._event_driver: _GameEventDriver | None = None
        self._update_callbacks: list[Callable[[float], None]] = []
        self._fixed_callbacks: list[Callable[[float], None]] = []
        self._input_callbacks: list[tuple[str, Callable[[], None]]] = []
        self._timers: list[_ScheduledCallback] = []
        self._callback_active = False
        self._gameplay_thread_id: int | None = None
        self._loop_mode: Literal["idle", "managed", "manual", "external"] = "idle"
        self._inside_tick = False
        self._stop_requested = False
        self._loop_finished = False
        self._closed = False
        self._pixels_per_unit = density
        self._texture_filter = filtering
        self._texture_mode = mapping
        self._texture_hot_reload = texture_hot_reload
        if auto_setup:
            from .lights import Light

            default_scene = Scene("Main")
            default_scene.camera = default_scene.camera.__class__(
                position=(4.5, 3.0, 6.5),
                vertical_fov_degrees=60.0,
            ).look_at((0.0, 0.0, 0.0))
            self._owned_default_scene = default_scene
            self.load_scene(default_scene)
            Light(
                "ambient",
                color=(0.55, 0.62, 0.75),
                intensity=0.16,
                scene=default_scene,
                _default=True,
            )
            key_light = Light(
                "directional",
                color=(1.0, 0.91, 0.78),
                intensity=0.95,
                casts_shadows=True,
                shadow_bias=0.0005,
                name="Directional Key Light",
                scene=default_scene,
                _default=True,
            )
            key_light.face_direction((-4.5, -7.0, -6.5))
            fill_light = Light(
                "directional",
                color=(0.72, 0.80, 1.0),
                intensity=0.55,
                casts_shadows=False,
                name="Directional Fill Light",
                scene=default_scene,
                _default=True,
            )
            # Keep the fill almost horizontal so it restores detail primarily
            # on the key light's rear X/Z faces rather than brightening the top.
            fill_light.face_direction((5.0, -0.75, 4.5))

    @property
    def scene(self) -> Scene | None:
        return self._scene

    @property
    def camera(self):
        """Persistent active-scene camera; assignments update native state."""

        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        return self._scene.camera

    @property
    def skybox(self):
        """Active scene sky; assign a path, ``Skybox``, ``'default'``, or ``None``."""

        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        return self._scene.skybox

    @skybox.setter
    def skybox(self, value) -> None:
        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        self._scene.skybox = value

    @property
    def lighting(self) -> Lighting:
        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        if self._lighting is None or self._lighting._scene is not self._scene:
            self._lighting = Lighting(self._scene)
        return self._lighting

    @property
    def input(self) -> Input:
        return self._input

    @property
    def audio(self) -> Audio:
        """Game-local decoded sounds and native playback voices."""

        return self._audio

    @property
    def is_running(self) -> bool:
        return self._engine.is_running

    @property
    def running(self) -> bool:
        """Whether a managed or manual loop should continue.

        This is initially true so ``while game.running: game.tick()`` enters
        without a separate start call. A close request, :meth:`stop`, or final
        :meth:`close` makes it false.
        """

        return not self._closed and not self._stop_requested and not self._loop_finished

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
    def pixels_per_unit(self) -> float:
        return self._pixels_per_unit

    @property
    def texture_filter(self) -> TextureFilter:
        return self._texture_filter

    @property
    def texture_mode(self) -> TextureMode:
        return self._texture_mode

    @property
    def texture_hot_reload(self) -> bool:
        return self._texture_hot_reload

    @property
    def scheduler_stats(self) -> SchedulerStats:
        return self._scheduler.stats

    @property
    def script_errors(self) -> tuple[str, ...]:
        return self._scheduler.errors

    def _begin_loop(self, mode: Literal["managed", "manual", "external"]) -> None:
        if self._closed:
            raise RuntimeError("cannot run a closed Game")
        if self._loop_mode != "idle":
            raise RuntimeError(
                f"cannot start {mode} loop while {self._loop_mode} loop is active"
            )
        self._scheduler.begin_run()
        self._gameplay_thread_id = threading.get_ident()
        self._loop_mode = mode
        self._stop_requested = False
        self._loop_finished = False

    def _advance_frame(self, delta_seconds: float) -> None:
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

    def _begin_external_loop(self) -> None:
        """Start scheduler ownership for a Pygame-controlled adapter."""

        self._begin_loop("external")

    def _advance_external_frame(self, delta_seconds: float) -> None:
        if self._loop_mode != "external":
            raise RuntimeError("the external RIX loop is not active")
        if self._gameplay_thread_id != threading.get_ident():
            raise RuntimeError("World.update() calls must stay on one thread")
        self._advance_frame(delta_seconds)

    def _finish_external_loop(self) -> None:
        if self._loop_mode != "external":
            return
        self._engine.end_external_window()
        self._finish_loop()

    def _finish_loop(self) -> None:
        if self._loop_mode == "idle":
            return
        self._callback_active = True
        try:
            if self._scene is not None:
                self._scene._commit_deferred(self._scheduler.destroy_callback)
        finally:
            self._callback_active = False
            self._inside_tick = False
            self._gameplay_thread_id = None
            self._loop_mode = "idle"
            self._loop_finished = True

    def run(self) -> None:
        """Run the managed native loop until close or :meth:`stop`."""

        self._begin_loop("managed")
        try:
            self._engine.run(self._advance_frame)
        finally:
            self._finish_loop()

    def tick(self, fps: float | None = None) -> float:
        """Pump, simulate, render, and present exactly one native frame.

        ``fps`` is an optional per-tick frame limit. ``None`` uses the limit
        configured on :class:`Game`; zero is unlimited. Registered callbacks
        and fixed physics use the same scheduler as :meth:`run`.
        """

        if fps is not None:
            if isinstance(fps, bool) or not isinstance(fps, (int, float)):
                raise TypeError("fps must be a number or None")
            if not math.isfinite(fps) or fps < 0:
                raise ValueError("fps must be zero (unlimited), positive, or None")
        if self._closed:
            raise RuntimeError("cannot tick a closed Game")
        if self._stop_requested:
            if self._loop_mode == "manual":
                self._engine.close()
                self._finish_loop()
            return 0.0
        if self._inside_tick:
            raise RuntimeError("recursive Game.tick() is not allowed")
        if self._loop_mode == "managed":
            raise RuntimeError("cannot call tick() while Game.run() is active")
        if self._loop_mode == "idle":
            self._begin_loop("manual")
        if self._gameplay_thread_id != threading.get_ident():
            raise RuntimeError("manual Game.tick() calls must stay on one thread")

        self._inside_tick = True
        try:
            elapsed = self._engine.tick(
                self._advance_frame,
                -1.0 if fps is None else float(fps),
            )
        except BaseException:
            if self._engine.is_running:
                self._engine.close()
            self._finish_loop()
            raise
        finally:
            self._inside_tick = False
        if not self._engine.is_running:
            self._finish_loop()
        return elapsed

    def stop(self) -> None:
        """Request a running game to stop; safe to call from another thread."""

        self._stop_requested = True
        self._engine.stop()

    def on_update(self, callback: Callable[[float], None]) -> Callable[[float], None]:
        if not callable(callback):
            raise TypeError("update callback must be callable")
        self._update_callbacks.append(callback)
        self._ensure_event_driver()
        return callback

    def update(self, callback: Callable[[float], None]) -> Callable[[float], None]:
        """Decorator alias for :meth:`on_update`."""

        return self.on_update(callback)

    def subscribe_update(self, callback: Callable[[float], None]) -> CallbackHandle:
        self.on_update(callback)
        return CallbackHandle(lambda: self._discard(self._update_callbacks, callback))

    def on_fixed_update(
        self, callback: Callable[[float], None]
    ) -> Callable[[float], None]:
        if not callable(callback):
            raise TypeError("fixed-update callback must be callable")
        self._fixed_callbacks.append(callback)
        self._ensure_event_driver()
        return callback

    def fixed_update(
        self, callback: Callable[[float], None]
    ) -> Callable[[float], None]:
        """Decorator alias for :meth:`on_fixed_update`."""

        return self.on_fixed_update(callback)

    def subscribe_fixed_update(
        self, callback: Callable[[float], None]
    ) -> CallbackHandle:
        self.on_fixed_update(callback)
        return CallbackHandle(lambda: self._discard(self._fixed_callbacks, callback))

    @overload
    def on_input(
        self, action: str, callback: Callable[[], None]
    ) -> Callable[[], None]: ...

    @overload
    def on_input(
        self, action: str, callback: None = None
    ) -> Callable[[Callable[[], None]], Callable[[], None]]: ...

    def on_input(
        self, action: str, callback: Callable[[], None] | None = None
    ) -> Callable[[], None] | Callable[[Callable[[], None]], Callable[[], None]]:
        if callback is None:
            return lambda registered: self.on_input(action, registered)  # type: ignore[return-value]
        if not callable(callback):
            raise TypeError("input callback must be callable")
        self._input_callbacks.append((action, callback))
        self._ensure_event_driver()
        return callback

    def subscribe_input(
        self, action: str, callback: Callable[[], None]
    ) -> CallbackHandle:
        self.on_input(action, callback)
        registration = (action, callback)
        return CallbackHandle(lambda: self._discard(self._input_callbacks, registration))

    def on_key(
        self, key: str
    ) -> Callable[[Callable[[], None]], Callable[[], None]]:
        """Bind a physical key and return a scheduler-thread decorator."""

        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        normalized = key.strip().lower().replace(" ", "_").replace("-", "_")
        action = f"key_{normalized}"
        self.input.bind(action, f"key:{normalized}")
        return self.on_input(action)  # type: ignore[return-value]

    def on_mouse(
        self, button: str
    ) -> Callable[[Callable[[], None]], Callable[[], None]]:
        """Bind a physical mouse button and return an edge callback decorator."""

        if not isinstance(button, str) or not button.strip():
            raise ValueError("mouse button must be a non-empty string")
        normalized = button.strip().lower().replace(" ", "_").replace("-", "_")
        action = f"mouse_{normalized}"
        self.input.bind(action, f"mouse:{normalized}")
        return self.on_input(action)  # type: ignore[return-value]

    def raycast(
        self,
        origin: Vec3 | tuple[float, float, float],
        direction: Vec3 | tuple[float, float, float],
        *,
        distance: float = 10.0,
        layers: Iterable[CollisionLayer] | None = None,
        include_triggers: bool = True,
        exclude: Entity | None = None,
    ) -> PhysicsHit | None:
        """Return the nearest hit in the active scene without passing it explicitly."""

        from .physics import raycast

        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        return raycast(
            self._scene,
            origin,
            direction,
            distance,
            layers=layers,
            include_triggers=include_triggers,
            exclude=exclude,
        )

    def play_sound(
        self,
        path: str | PathLike[str],
        *,
        volume: float = 1.0,
        loop: bool = False,
        position: Vec3 | tuple[float, float, float] | None = None,
        minimum_distance: float = 1.0,
        maximum_distance: float = 50.0,
    ) -> AudioSource:
        """Load through the game cache and play a WAV in one call."""

        sound = self._audio.load(Path(path))
        return self._audio.play(
            sound,
            volume=volume,
            loop=loop,
            position=position,
            minimum_distance=minimum_distance,
            maximum_distance=maximum_distance,
        )

    def manage_timer(self, timer: Timer, *, start: bool = True) -> CallbackHandle:
        """Advance a standalone Timer on its declared clock exactly once."""

        from .utilities import ClockDomain, Timer

        if not isinstance(timer, Timer):
            raise TypeError("timer must be an rix.Timer")
        existing = getattr(timer, "_rix_handle", None)
        if existing is not None and existing.active:
            raise ValueError("timer is already managed")
        if start and not timer.running and not timer.finished:
            timer.start()
        handle: CallbackHandle

        def advance(delta: float) -> None:
            if timer.time_domain is ClockDomain.WALL:
                timer.poll()
            else:
                timer.advance(delta, time_domain=timer.time_domain)
            if timer.finished or timer.cancelled:
                handle.cancel()

        handle = (
            self.subscribe_fixed_update(advance)
            if timer.time_domain is ClockDomain.SIMULATION
            else self.subscribe_update(advance)
        )
        timer._rix_handle = handle
        return handle

    def manage_state_machine(
        self,
        machine: StateMachine,
        *,
        active: Callable[[], bool] | None = None,
    ) -> CallbackHandle:
        """Update a started StateMachine once per render update."""

        from .utilities import StateMachine

        if not isinstance(machine, StateMachine):
            raise TypeError("machine must be an rix.StateMachine")
        if machine.current is None and machine._initial is None:
            raise RuntimeError(
                "state machine must be started or declare an initial state before it is managed"
            )
        existing = getattr(machine, "_rix_handle", None)
        if existing is not None and existing.active:
            raise ValueError("state machine is already managed")
        if active is not None and not callable(active):
            raise TypeError("active must be callable or None")

        def update_machine(delta_seconds: float) -> None:
            if active is None or bool(active()):
                machine.update(delta_seconds)

        handle = self.subscribe_update(update_machine)
        machine._rix_handle = handle
        return handle

    def manage_tween(self, tween: Tween[Any]) -> CallbackHandle:
        """Advance a Tween on its declared clock exactly once."""

        from .utilities import ClockDomain, Tween

        if not isinstance(tween, Tween):
            raise TypeError("tween must be an rix.Tween")
        existing = getattr(tween, "_rix_handle", None)
        if existing is not None and existing.active:
            raise ValueError("tween is already managed")
        if not tween.running and not tween.finished:
            tween.start()
        handle: CallbackHandle

        def advance(delta: float) -> None:
            if tween.time_domain is ClockDomain.WALL:
                tween.poll()
            else:
                tween.advance(delta, time_domain=tween.time_domain)
            if tween.finished:
                handle.cancel()

        handle = (
            self.subscribe_fixed_update(advance)
            if tween.time_domain is ClockDomain.SIMULATION
            else self.subscribe_update(advance)
        )
        tween._rix_handle = handle
        return handle

    def after(self, seconds: float, callback: Callable[[], None]) -> CallbackHandle:
        """Schedule once using render/game-loop time and return cancellation."""

        delay = float(seconds)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be finite and non-negative")
        if not callable(callback):
            raise TypeError("timer callback must be callable")
        timer = _ScheduledCallback(delay, None, callback)
        handle = CallbackHandle(lambda: self._cancel_timer(timer))
        timer.handle = handle
        self._timers.append(timer)
        self._ensure_event_driver()
        return handle

    def every(self, seconds: float, callback: Callable[[], None]) -> CallbackHandle:
        """Schedule repeatedly using render/game-loop time and return cancellation."""

        interval = float(seconds)
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        if not callable(callback):
            raise TypeError("timer callback must be callable")
        timer = _ScheduledCallback(interval, interval, callback)
        handle = CallbackHandle(lambda: self._cancel_timer(timer))
        timer.handle = handle
        self._timers.append(timer)
        self._ensure_event_driver()
        return handle

    def on_collision(
        self,
        entity: object,
        callback: Callable[[object], None] | None = None,
        *,
        phase: Literal["enter", "stay", "exit"] = "enter",
        trigger: bool = False,
    ) -> None | Callable[[Callable[[object], None]], Callable[[object], None]]:
        from .entity import Entity

        if not isinstance(entity, Entity):
            raise TypeError("entity must be an rix.Entity")
        if callback is None:
            def decorator(registered: Callable[[object], None]) -> Callable[[object], None]:
                self.on_collision(entity, registered, phase=phase, trigger=trigger)
                return registered

            return decorator
        if not callable(callback):
            raise TypeError("collision callback must be callable")
        if phase not in ("enter", "stay", "exit"):
            raise ValueError("phase must be enter, stay, or exit")
        if not isinstance(trigger, bool):
            raise TypeError("trigger must be a bool")
        hook = f"on_{'trigger' if trigger else 'collision'}_{phase}"
        setattr(entity, hook, callback)
        entity.scene._register_script_entity(entity)
        return None

    @staticmethod
    def _discard(values: list[Any], value: object) -> None:
        try:
            values.remove(value)
        except ValueError:
            pass

    def _cancel_timer(self, timer: _ScheduledCallback) -> None:
        timer.cancelled = True
        self._discard(self._timers, timer)

    def _ensure_event_driver(self) -> None:
        if self._scene is not None and self._event_driver is None:
            self._event_driver = _GameEventDriver(self, self._scene)

    def load_scene(self, scene: Scene) -> None:
        """Make ``scene`` this game's active scene.

        A scene can be loaded by only one game at a time. Replacing a scene
        deactivates it but does not destroy its entities.
        """

        if not isinstance(scene, Scene):
            raise TypeError("scene must be an rix.Scene")
        if self.is_running:
            raise RuntimeError("cannot replace the active scene while Game is running")
        if self._scene is scene:
            return
        scene._configure_textures(
            pixels_per_unit=self._pixels_per_unit,
            texture_filter=self._texture_filter,
            texture_mode=self._texture_mode,
            hot_reload=self._texture_hot_reload,
        )
        scene._attach(self)
        self._engine.set_scene(scene._native)
        previous = self._scene
        self._scene = scene
        self._lighting = Lighting(scene)
        self._event_driver = None
        Scene._set_default(scene, self)
        if previous is not None:
            for entity in previous._script_snapshot():
                cancel = getattr(entity, "_cancel_managed", None)
                if callable(cancel):
                    cancel()
            previous._detach(self)
            if previous is self._owned_default_scene and previous is not scene:
                previous.close()
                self._owned_default_scene = None
        if (
            self._update_callbacks
            or self._fixed_callbacks
            or self._input_callbacks
            or self._timers
        ):
            self._ensure_event_driver()

    def unload_scene(self, *, clear: bool = False) -> Scene | None:
        """Deactivate and return the current scene, optionally clearing it."""

        scene = self._scene
        if scene is None:
            return None
        if self.is_running:
            raise RuntimeError("cannot unload the active scene while Game is running")
        if clear:
            scene.clear()
        else:
            for entity in scene._script_snapshot():
                cancel = getattr(entity, "_cancel_managed", None)
                if callable(cancel):
                    cancel()
        scene._detach(self)
        self._engine.set_scene(None)
        self._scene = None
        self._lighting = None
        self._event_driver = None
        if Scene._default() is scene:
            Scene._set_default(None)
        return scene

    def close(self) -> None:
        """Detach and clean up an owned automatic scene; idempotent."""

        if self._closed:
            return
        if self._loop_mode == "managed" or self._inside_tick:
            raise RuntimeError("cannot close a Game while its frame loop is active")
        if self._loop_mode == "manual":
            self._engine.close()
            self._finish_loop()
        scene = self.unload_scene(clear=True)
        if scene is not None and scene is self._owned_default_scene:
            scene.close()
        self._owned_default_scene = None
        self._update_callbacks.clear()
        self._fixed_callbacks.clear()
        self._input_callbacks.clear()
        for timer in self._timers:
            timer.cancelled = True
            if timer.handle is not None:
                timer.handle._active = False
        self._timers.clear()
        self._closed = True
        self._stop_requested = True
        self._loop_finished = True

    def __enter__(self) -> Game:
        if self._scene is None:
            raise RuntimeError("Game has no active scene")
        Scene._set_default(self._scene, self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _allows_scene_mutation(self, scene: Scene) -> bool:
        return (
            scene is self._scene
            and self._gameplay_thread_id == threading.get_ident()
            and (
                self._callback_active
                or (
                    self._loop_mode in ("manual", "external")
                    and not self._inside_tick
                )
            )
        )

    def _on_entity_destroyed(self, entity: object) -> None:
        cancel = getattr(entity, "_cancel_managed", None)
        if callable(cancel):
            cancel()
        self._scheduler.forget(entity)  # type: ignore[arg-type]

