"""Deterministic Python script lifecycle and fixed-step scheduling."""

from __future__ import annotations

import math
import sys
import time
import traceback
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .entity import Entity
    from .scene import Scene


class ScriptCallbackError(RuntimeError):
    """A gameplay callback failed in fail-fast mode."""


@dataclass(frozen=True, slots=True)
class CallbackStats:
    calls: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0
    last_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class SchedulerStats:
    fixed_ticks: int
    overrun_count: int
    dropped_seconds: float
    callbacks: Mapping[str, CallbackStats]


@dataclass(slots=True)
class _MutableCallbackStats:
    calls: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0
    last_seconds: float = 0.0

    def add(self, duration: float) -> None:
        self.calls += 1
        self.total_seconds += duration
        self.max_seconds = max(self.max_seconds, duration)
        self.last_seconds = duration

    def snapshot(self) -> CallbackStats:
        return CallbackStats(
            self.calls, self.total_seconds, self.max_seconds, self.last_seconds
        )


@dataclass(slots=True)
class _Lifecycle:
    awake: bool = False
    started: bool = False


class SimulationScheduler:
    """Runs entity hooks at safe render and fixed-step boundaries."""

    def __init__(
        self,
        *,
        fixed_hz: float = 60.0,
        max_frame_seconds: float = 0.25,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
    ) -> None:
        if not math.isfinite(fixed_hz) or fixed_hz <= 0:
            raise ValueError("fixed_hz must be finite and positive")
        if not math.isfinite(max_frame_seconds) or max_frame_seconds <= 0:
            raise ValueError("max_frame_seconds must be finite and positive")
        if (isinstance(max_catch_up_steps, bool) or
                not isinstance(max_catch_up_steps, int) or
                max_catch_up_steps <= 0):
            raise ValueError("max_catch_up_steps must be a positive integer")
        self.fixed_dt = 1.0 / float(fixed_hz)
        self.max_frame_seconds = float(max_frame_seconds)
        self.max_catch_up_steps = int(max_catch_up_steps)
        self.fail_fast = bool(fail_fast)
        self._accumulator = 0.0
        self._fixed_ticks = 0
        self._overrun_count = 0
        self._dropped_seconds = 0.0
        self._profiles: dict[str, _MutableCallbackStats] = {}
        self._lifecycle: dict[tuple[int, int], _Lifecycle] = {}
        self._failed: set[tuple[int, int]] = set()
        self._errors: list[str] = []

    def begin_run(self) -> None:
        self._accumulator = 0.0
        self._fixed_ticks = 0
        self._overrun_count = 0
        self._dropped_seconds = 0.0
        self._profiles.clear()
        self._errors.clear()

    @property
    def stats(self) -> SchedulerStats:
        callbacks = MappingProxyType(
            {name: stats.snapshot() for name, stats in self._profiles.items()}
        )
        return SchedulerStats(
            self._fixed_ticks,
            self._overrun_count,
            self._dropped_seconds,
            callbacks,
        )

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self._errors)

    def forget(self, entity: Entity) -> None:
        key = self._key(entity)
        self._lifecycle.pop(key, None)
        self._failed.discard(key)

    def advance(self, scene: Scene | None, frame_seconds: float) -> None:
        if scene is None:
            return
        raw_delta = float(frame_seconds)
        if not math.isfinite(raw_delta) or raw_delta < 0:
            raise ValueError("frame_seconds must be finite and non-negative")
        delta = min(raw_delta, self.max_frame_seconds)
        self._prepare_lifecycle(scene)
        self._accumulator += delta

        steps = 0
        while self._accumulator + 1.0e-12 >= self.fixed_dt:
            if steps >= self.max_catch_up_steps:
                retained = math.fmod(self._accumulator, self.fixed_dt)
                self._dropped_seconds += self._accumulator - retained
                self._accumulator = retained
                self._overrun_count += 1
                break
            self._run_hook(scene, "fixed_update", self.fixed_dt)
            scene._native.step_physics(self.fixed_dt)
            self._fixed_ticks += 1
            self._accumulator -= self.fixed_dt
            steps += 1

        self._run_hook(scene, "update", delta)
        self._run_hook(scene, "late_update", delta)

    def destroy_callback(self, entity: Entity) -> None:
        self._invoke(entity, "on_destroy", force=True)
        self.forget(entity)

    def _prepare_lifecycle(self, scene: Scene) -> None:
        for entity in scene._script_snapshot():
            key = self._key(entity)
            state = self._lifecycle.setdefault(key, _Lifecycle())
            if not state.awake and entity.is_alive:
                self._invoke(entity, "awake")
                state.awake = True
        scene._commit_deferred(self.destroy_callback)

        for entity in scene._script_snapshot():
            key = self._key(entity)
            state = self._lifecycle.setdefault(key, _Lifecycle())
            if state.awake and not state.started and entity.is_alive and entity.enabled:
                self._invoke(entity, "start")
                state.started = True
        scene._commit_deferred(self.destroy_callback)

    def _run_hook(self, scene: Scene, hook: str, delta: float) -> None:
        for entity in scene._script_snapshot():
            state = self._lifecycle.setdefault(self._key(entity), _Lifecycle())
            if entity.is_alive and entity.enabled and state.started:
                self._invoke(entity, hook, delta)
        scene._commit_deferred(self.destroy_callback)

    def _invoke(
        self,
        entity: Entity,
        hook: str,
        *arguments: float,
        force: bool = False,
    ) -> None:
        callback = getattr(entity, hook, None)
        if not callable(callback):
            return
        key = self._key(entity)
        if key in self._failed and not force:
            return
        started = time.perf_counter()
        try:
            callback(*arguments)
        except BaseException as error:
            message = (
                f"{hook} failed for {type(entity).__name__} "
                f"name={entity.name!r} id={entity.id}: {error}"
            )
            self._errors.append(message)
            self._failed.add(key)
            if self.fail_fast:
                raise ScriptCallbackError(message) from error
            print(message, file=sys.stderr)
            traceback.print_exception(error, file=sys.stderr)
        finally:
            duration = time.perf_counter() - started
            self._profiles.setdefault(hook, _MutableCallbackStats()).add(duration)

    @staticmethod
    def _key(entity: Entity) -> tuple[int, int]:
        return entity.scene.world_id, entity.id
