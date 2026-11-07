"""Pygame-friendly screen stacks with safe deferred transitions."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ScreenTimer:
    screen: str
    target: str
    duration: float
    elapsed: float = 0.0
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(frozen=True, slots=True)
class ScreenPolicy:
    """Controls whether a stacked screen exposes the screens below it.

    Events travel from the top downward. Updates and drawing travel from the
    lowest included screen upward. ``update_underlay`` applies to both variable
    and fixed updates, while ``event_underlay`` applies to forwarded input and
    other Pygame events.
    """

    update_underlay: bool = False
    event_underlay: bool = False
    draw_underlay: bool = True

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool)
            for value in (
                self.update_underlay,
                self.event_underlay,
                self.draw_underlay,
            )
        ):
            raise TypeError("screen propagation options must be bools")


class GameStates:
    """Small screen manager for menus, gameplay, and pause overlays."""

    def __init__(self, initial: str) -> None:
        self._name(initial)
        self._initial = initial
        self._registry: dict[str, type[object] | object] = {}
        self._policies: dict[str, ScreenPolicy] = {}
        self._registrations: dict[int, str] = {}
        self._instances: dict[str, object] = {}
        self._stack: list[str] = []
        self._busy = False
        self._pending: tuple[str, str | None] | None = None
        self._timers: list[ScreenTimer] = []
        self._closed = False

    @property
    def current(self) -> str | None:
        return self._stack[-1] if self._stack else None

    @property
    def stack(self) -> tuple[str, ...]:
        return tuple(self._stack)

    @property
    def registered(self) -> tuple[str, ...]:
        return tuple(self._registry)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def screen_object(self) -> object | None:
        current = self.current
        return self._instance(current) if current is not None else None

    def screen(
        self,
        name: str,
        *,
        update_underlay: bool = False,
        event_underlay: bool = False,
        draw_underlay: bool = True,
    ) -> Callable[[type[object] | object], type[object] | object]:
        """Register one class or object under exactly one screen name.

        The default policy implements a paused overlay: only the top screen
        receives events and updates, while every screen remains visible.
        """

        self._require_open()
        self._name(name)
        policy = ScreenPolicy(update_underlay, event_underlay, draw_underlay)

        def register(value: type[object] | object) -> type[object] | object:
            self._require_open()
            if name in self._registry:
                raise ValueError(f"screen {name!r} is already registered")
            previous = self._registrations.get(id(value))
            if previous is not None:
                raise ValueError(
                    f"screen object is already registered as {previous!r}"
                )
            self._registry[name] = value
            self._policies[name] = policy
            self._registrations[id(value)] = name
            if name == self._initial and not self._stack:
                self._stack.append(name)
                self._call(self._instance(name), "enter", None)
            return value

        return register

    def get(self, name: str) -> object:
        """Return the single manager-owned instance for ``name``."""

        self._require_open()
        self._require_screen(name)
        return self._instance(name)

    def policy(self, name: str) -> ScreenPolicy:
        self._require_open()
        self._require_screen(name)
        return self._policies[name]

    def change(self, name: str) -> None:
        self._require_open()
        self._require_screen(name)
        if self._busy:
            self._pending = ("change", name)
            return
        if self.current == name and len(self._stack) == 1:
            return
        previous = self.current
        for old_name in reversed(self._stack):
            self._call(self._instance(old_name), "exit", name)
            self._cancel_timers(old_name)
        self._stack[:] = [name]
        self._call(self._instance(name), "enter", previous)

    def push(self, name: str) -> None:
        self._require_open()
        self._require_screen(name)
        if self._busy:
            self._pending = ("push", name)
            return
        if name in self._stack:
            raise ValueError(f"screen {name!r} is already on the stack")
        previous = self.current
        self._stack.append(name)
        self._call(self._instance(name), "enter", previous)

    def pop(self) -> str:
        self._require_open()
        if self._busy:
            self._pending = ("pop", None)
            return self.current or ""
        if len(self._stack) <= 1:
            raise RuntimeError("cannot pop the final game screen")
        removed = self._stack.pop()
        self._call(self._instance(removed), "exit", self.current)
        self._cancel_timers(removed)
        return removed

    def event(self, event: object) -> None:
        self._forward("event", event, propagation="event")

    def update(self, delta_seconds: float) -> None:
        delta = self._delta(delta_seconds)
        names = self._dispatch_names("update")
        self._forward_names(names, "update", delta)
        self._advance_timers(delta, names)

    def fixed_update(self, delta_seconds: float) -> None:
        delta = self._delta(delta_seconds)
        self._forward("fixed_update", delta, propagation="update")

    def draw(self, surface: object) -> None:
        self._forward_names(self._dispatch_names("draw"), "draw", surface)

    def after(
        self, seconds: float, target: str, *, screen: str | None = None
    ) -> ScreenTimer:
        self._require_open()
        self._require_screen(target)
        owner = screen if screen is not None else self.current
        if owner is None:
            raise RuntimeError("after() requires an active or explicit screen")
        self._require_screen(owner)
        duration = float(seconds)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("seconds must be finite and positive")
        timer = ScreenTimer(owner, target, duration)
        self._timers.append(timer)
        return timer

    def close(self) -> None:
        if self._closed:
            return
        if self._busy:
            raise RuntimeError("cannot close GameStates from inside a callback")
        for name in reversed(self._stack):
            self._call(self._instance(name), "exit", None)
            self._cancel_timers(name)
        self._stack.clear()
        self._pending = None
        for timer in self._timers:
            timer.cancelled = True
        self._timers.clear()
        self._instances.clear()
        self._closed = True

    def _forward(
        self,
        method: str,
        *args: object,
        propagation: str,
    ) -> None:
        self._forward_names(self._dispatch_names(propagation), method, *args)

    def _forward_names(
        self, names: tuple[str, ...], method: str, *args: object
    ) -> None:
        self._busy = True
        try:
            for name in names:
                self._call(self._instance(name), method, *args)
        finally:
            self._busy = False
        self._commit_pending()

    def _dispatch_names(self, propagation: str) -> tuple[str, ...]:
        self._require_open()
        if not self._stack:
            raise RuntimeError("the initial screen has not been registered")
        stack = tuple(self._stack)
        if propagation == "draw":
            start = 0
            for index in range(len(stack) - 1, -1, -1):
                if not self._policies[stack[index]].draw_underlay:
                    start = index
                    break
            return stack[start:]
        if propagation not in ("event", "update"):
            raise ValueError("unknown screen propagation kind")
        selected = [stack[-1]]
        attribute = (
            "event_underlay" if propagation == "event" else "update_underlay"
        )
        for index in range(len(stack) - 1, 0, -1):
            if not getattr(self._policies[stack[index]], attribute):
                break
            selected.append(stack[index - 1])
        if propagation == "update":
            selected.reverse()
        return tuple(selected)

    def _commit_pending(self) -> None:
        pending = self._pending
        self._pending = None
        if pending is None:
            return
        operation, name = pending
        if operation == "change":
            assert name is not None
            self.change(name)
        elif operation == "push":
            assert name is not None
            self.push(name)
        else:
            self.pop()

    def _advance_timers(self, delta: float, updated: tuple[str, ...]) -> None:
        updated_names = frozenset(updated)
        for timer in tuple(self._timers):
            if (
                timer.cancelled
                or timer.screen not in updated_names
                or timer.screen not in self._stack
            ):
                continue
            timer.elapsed += delta
            if timer.elapsed + 1.0e-12 >= timer.duration:
                timer.cancelled = True
                self.change(timer.target)
                break

    def _cancel_timers(self, screen: str) -> None:
        for timer in self._timers:
            if timer.screen == screen:
                timer.cancelled = True

    def _instance(self, name: str) -> object:
        try:
            return self._instances[name]
        except KeyError:
            registered = self._registry[name]
            value = registered() if isinstance(registered, type) else registered
            self._instances[name] = value
            return value

    @staticmethod
    def _call(screen: object, method: str, *args: object) -> Any:
        callback = getattr(screen, method, None)
        return callback(*args) if callback is not None else None

    def _require_screen(self, name: str) -> None:
        self._name(name)
        if name not in self._registry:
            raise KeyError(f"unknown screen {name!r}")

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("GameStates is closed")

    @staticmethod
    def _name(name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("screen name must be a non-empty string")

    @staticmethod
    def _delta(value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("delta_seconds must be a number")
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError("delta_seconds must be finite and non-negative")
        return result


__all__ = ["GameStates", "ScreenPolicy", "ScreenTimer"]
