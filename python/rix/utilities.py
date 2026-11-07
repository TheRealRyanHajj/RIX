"""Graphics-independent gameplay state, timing, event, and tween utilities."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Generic, TypeVar, cast


class ClockDomain(str, Enum):
    """Clock that owns a timer or tween."""

    WALL = "wall"
    RENDER = "render"
    SIMULATION = "simulation"


class Easing(str, Enum):
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


def _clock_domain(value: ClockDomain | str) -> ClockDomain:
    try:
        return ClockDomain(value)
    except ValueError as error:
        choices = ", ".join(item.value for item in ClockDomain)
        raise ValueError(f"time_domain must be one of: {choices}") from error


def _duration(value: float, name: str = "duration") -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _delta(value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("delta_seconds must be finite and non-negative")
    return result


def _boolean(value: bool, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


EnterCallback = Callable[[str | None], None]
UpdateCallback = Callable[[float], None]
ExitCallback = Callable[[str | None], None]
TransitionGuard = Callable[[], bool]


class AnimationSelection:
    """Runtime clip selection state without claiming renderer skinning playback."""

    def __init__(self) -> None:
        self._current: str | None = None
        self._previous: str | None = None
        self._revision = 0

    @property
    def current(self) -> str | None:
        return self._current

    @property
    def previous(self) -> str | None:
        return self._previous

    @property
    def revision(self) -> int:
        """Increments only when selection or explicit restart changes playback state."""

        return self._revision

    def play(self, name: str, *, restart: bool = False) -> bool:
        if not isinstance(name, str) or not name:
            raise ValueError("animation name must be a non-empty string")
        if not isinstance(restart, bool):
            raise TypeError("restart must be a bool")
        if name == self._current and not restart:
            return False
        self._previous = self._current
        self._current = name
        self._revision += 1
        return True

    def stop(self) -> bool:
        if self._current is None:
            return False
        self._previous = self._current
        self._current = None
        self._revision += 1
        return True


@dataclass(frozen=True, slots=True)
class State:
    """Named state and its optional lifecycle callbacks."""

    name: str
    on_enter: EnterCallback | None = None
    on_update: UpdateCallback | None = None
    on_exit: ExitCallback | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("state name must be a non-empty string")
        for name, callback in (
            ("on_enter", self.on_enter),
            ("on_update", self.on_update),
            ("on_exit", self.on_exit),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable or None")


@dataclass(frozen=True, slots=True)
class Transition:
    source: str
    target: str
    event: str
    guard: TransitionGuard | None = None
    priority: int = 0


@dataclass(slots=True)
class TimedTransition:
    """Cancelable one-shot transition owned by one source state."""

    source: str
    target: str
    duration: float
    elapsed: float = 0.0
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(frozen=True, slots=True)
class _ConditionalTransition:
    source: str
    target: str
    condition: TransitionGuard
    priority: int
    order: int


class StateMachine:
    """Deterministic state machine with simple and advanced APIs."""

    def __init__(
        self,
        initial: str | None = None,
        *,
        max_transitions_per_update: int = 8,
    ) -> None:
        if initial is not None and (not isinstance(initial, str) or not initial):
            raise ValueError("initial state must be a non-empty string or None")
        if (
            isinstance(max_transitions_per_update, bool)
            or not isinstance(max_transitions_per_update, int)
            or max_transitions_per_update <= 0
        ):
            raise ValueError("max_transitions_per_update must be a positive integer")
        self._states: dict[str, State] = {}
        self._transitions: dict[tuple[str, str], list[Transition]] = {}
        self._conditions: list[_ConditionalTransition] = []
        self._timers: list[TimedTransition] = []
        self._animations: dict[str, str] = {}
        self._animation_selection: AnimationSelection | None = None
        self._initial = initial
        self._current: str | None = None
        self._previous: str | None = None
        self._time_in_state = 0.0
        self._busy = False
        self._paused = False
        self._deferred: str | None = None
        self._next_order = 0
        self._max_transitions_per_update = max_transitions_per_update

    @property
    def current(self) -> str | None:
        return self._current

    @property
    def previous(self) -> str | None:
        return self._previous

    @property
    def time_in_state(self) -> float:
        return self._time_in_state

    @property
    def elapsed(self) -> float:
        return self._time_in_state

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def states(self) -> tuple[str, ...]:
        return tuple(self._states)

    def state(
        self, name: str, *, animation: str | None = None
    ) -> Callable[[UpdateCallback], UpdateCallback]:
        """Register an update function using beginner-friendly decorator syntax."""

        if animation is not None and (
            not isinstance(animation, str) or not animation
        ):
            raise ValueError("animation must be a non-empty string or None")

        def register(callback: UpdateCallback) -> UpdateCallback:
            if not callable(callback):
                raise TypeError("state callback must be callable")
            self.add_state(name, on_update=callback)
            if animation is not None:
                self._animations[name] = animation
            return callback

        return register

    def bind_animations(self, selection: AnimationSelection) -> None:
        if not isinstance(selection, AnimationSelection):
            raise TypeError("selection must be an rix.AnimationSelection")
        self._animation_selection = selection
        if self._current is not None:
            self._select_animation(self._current)

    def enter(
        self, name: str
    ) -> Callable[[EnterCallback], EnterCallback]:
        def register(callback: EnterCallback) -> EnterCallback:
            if not callable(callback):
                raise TypeError("enter callback must be callable")
            self._replace_callbacks(name, on_enter=callback)
            return callback

        return register

    def exit(
        self, name: str
    ) -> Callable[[ExitCallback], ExitCallback]:
        def register(callback: ExitCallback) -> ExitCallback:
            if not callable(callback):
                raise TypeError("exit callback must be callable")
            self._replace_callbacks(name, on_exit=callback)
            return callback

        return register

    def add_state(
        self,
        state: State | str,
        *,
        on_enter: EnterCallback | None = None,
        on_update: UpdateCallback | None = None,
        on_exit: ExitCallback | None = None,
    ) -> State:
        self._require_idle()
        if isinstance(state, str):
            state = State(state, on_enter, on_update, on_exit)
        elif any(callback is not None for callback in (on_enter, on_update, on_exit)):
            raise TypeError("callbacks cannot be supplied with an existing State")
        elif not isinstance(state, State):
            raise TypeError("state must be a State or name string")
        if state.name in self._states:
            raise ValueError(f"state {state.name!r} is already registered")
        self._states[state.name] = state
        return state

    def add_transition(
        self,
        source: str,
        target: str,
        event: str,
        *,
        guard: TransitionGuard | None = None,
        priority: int = 0,
    ) -> Transition:
        self._require_idle()
        self._require_state(source)
        self._require_state(target)
        if not isinstance(event, str) or not event:
            raise ValueError("transition event must be a non-empty string")
        if guard is not None and not callable(guard):
            raise TypeError("transition guard must be callable or None")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("transition priority must be an integer")
        transition = Transition(source, target, event, guard, priority)
        bucket = self._transitions.setdefault((source, event), [])
        if any(item.target == target and item.guard is guard for item in bucket):
            raise ValueError("duplicate transition")
        bucket.append(transition)
        bucket.sort(key=lambda item: -item.priority)
        return transition

    def when(
        self,
        source: str,
        target: str,
        *,
        condition: TransitionGuard,
        priority: int = 0,
    ) -> _ConditionalTransition:
        self._require_idle()
        self._require_state(source)
        self._require_state(target)
        if not callable(condition):
            raise TypeError("condition must be callable")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("transition priority must be an integer")
        self._next_order += 1
        transition = _ConditionalTransition(
            source, target, condition, priority, self._next_order
        )
        self._conditions.append(transition)
        self._conditions.sort(key=lambda item: (-item.priority, item.order))
        return transition

    def after(
        self,
        seconds: float,
        target: str,
        *,
        state: str | None = None,
    ) -> TimedTransition:
        self._require_idle()
        self._require_state(target)
        source = state if state is not None else self._current or self._initial
        if source is None:
            raise RuntimeError("after() needs a current, initial, or explicit source state")
        self._require_state(source)
        timer = TimedTransition(source, target, _duration(seconds, "seconds"))
        self._timers.append(timer)
        return timer

    def start(self, state: str) -> None:
        self._require_idle()
        self._require_state(state)
        if self._current is not None:
            raise RuntimeError("state machine is already started")
        self._busy = True
        try:
            self._current = state
            self._previous = None
            self._time_in_state = 0.0
            self._select_animation(state)
            callback = self._states[state].on_enter
            if callback is not None:
                try:
                    callback(None)
                except BaseException:
                    self._current = None
                    self._time_in_state = 0.0
                    if self._animation_selection is not None:
                        self._animation_selection.stop()
                    raise
        finally:
            self._busy = False

    def stop(self) -> None:
        self._require_idle()
        if self._current is None:
            return
        self._busy = True
        try:
            current = self._current
            callback = self._states[current].on_exit
            if callback is not None:
                callback(None)
            self._previous = current
            self._current = None
            self._time_in_state = 0.0
            self._cancel_timers(current)
        finally:
            self._busy = False

    def update(self, delta_seconds: float) -> None:
        delta = _delta(delta_seconds)
        self._require_idle()
        if self._paused:
            return
        if self._current is None and self._initial is not None:
            self.start(self._initial)
        current = self._require_started()
        self._busy = True
        try:
            callback = self._states[current].on_update
            if callback is not None:
                callback(delta)
            self._time_in_state += delta
        finally:
            self._busy = False
        self._commit_deferred()
        self._advance_timers(delta)
        self._evaluate_conditions()

    def trigger(self, event: str) -> bool:
        self._require_idle()
        current = self._require_started()
        if not isinstance(event, str) or not event:
            raise ValueError("transition event must be a non-empty string")
        self._busy = True
        try:
            for transition in self._transitions.get((current, event), ()):
                if transition.guard is None or bool(transition.guard()):
                    self._perform_transition(transition.target)
                    return True
            return False
        finally:
            self._busy = False

    def transition_to(self, target: str) -> bool:
        """Perform an explicit transition without requiring a registered event."""

        self._require_idle()
        self._require_started()
        self._require_state(target)
        if target == self._current:
            return False
        self._busy = True
        try:
            self._perform_transition(target)
            return True
        finally:
            self._busy = False

    def change(self, target: str) -> bool:
        """Change immediately, or safely defer until the active callback returns."""

        self._require_state(target)
        if target == self._current or target == self._deferred:
            return False
        if self._current is None:
            self.start(target)
            return True
        if self._busy:
            self._deferred = target
            return True
        return self.transition_to(target)

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def reset(self, state: str | None = None) -> None:
        self._require_idle()
        target = state if state is not None else self._initial
        if target is not None:
            self._require_state(target)
        if self._current is not None:
            self.stop()
        self._previous = None
        self._time_in_state = 0.0
        self._paused = False
        self._deferred = None
        for timer in self._timers:
            timer.cancelled = True
        if target is not None:
            self.start(target)

    def _perform_transition(self, target: str) -> None:
        source = self._require_started()
        exit_callback = self._states[source].on_exit
        if exit_callback is not None:
            exit_callback(target)
        self._previous = source
        self._current = target
        self._time_in_state = 0.0
        self._cancel_timers(source)
        self._select_animation(target)
        enter_callback = self._states[target].on_enter
        if enter_callback is not None:
            try:
                enter_callback(source)
            except BaseException:
                self._current = source
                self._previous = None
                self._time_in_state = 0.0
                self._select_animation(source)
                raise

    def _replace_callbacks(
        self,
        name: str,
        *,
        on_enter: EnterCallback | None = None,
        on_exit: ExitCallback | None = None,
    ) -> None:
        self._require_idle()
        self._require_state(name)
        state = self._states[name]
        self._states[name] = State(
            name,
            on_enter if on_enter is not None else state.on_enter,
            state.on_update,
            on_exit if on_exit is not None else state.on_exit,
        )

    def _commit_deferred(self) -> None:
        target = self._deferred
        self._deferred = None
        if target is not None and target != self._current:
            self.transition_to(target)

    def _advance_timers(self, delta: float) -> None:
        current = self._current
        if current is None:
            return
        for timer in tuple(self._timers):
            if timer.cancelled or timer.source != current:
                continue
            timer.elapsed += delta
            if timer.elapsed + 1.0e-12 >= timer.duration:
                timer.cancelled = True
                self.change(timer.target)
                break

    def _evaluate_conditions(self) -> None:
        transitions = 0
        while transitions < self._max_transitions_per_update:
            current = self._current
            selected = next(
                (
                    item
                    for item in self._conditions
                    if item.source == current and bool(item.condition())
                ),
                None,
            )
            if selected is None:
                return
            if selected.target == current:
                return
            self.transition_to(selected.target)
            transitions += 1
        if any(item.source == self._current and bool(item.condition()) for item in self._conditions):
            raise RuntimeError("state transition limit exceeded during one update")

    def _cancel_timers(self, source: str) -> None:
        for timer in self._timers:
            if timer.source == source:
                timer.cancelled = True

    def _select_animation(self, state: str) -> None:
        selection = self._animation_selection
        animation = self._animations.get(state)
        if selection is not None and animation is not None:
            selection.play(animation)

    def _require_state(self, name: str) -> None:
        if name not in self._states:
            raise KeyError(f"unknown state {name!r}")

    def _require_started(self) -> str:
        if self._current is None:
            raise RuntimeError("state machine has not been started")
        return self._current

    def _require_idle(self) -> None:
        if self._busy:
            raise RuntimeError("reentrant state-machine operation is not allowed")


TimerCallback = Callable[["Timer"], None]


class Timer:
    """Advanceable timer owned by wall, render, or simulation time."""

    _MAX_CALLBACKS_PER_ADVANCE = 1_000

    def __init__(
        self,
        duration: float,
        *,
        repeat: bool = False,
        autostart: bool = False,
        time_domain: ClockDomain | str = ClockDomain.SIMULATION,
        callback: TimerCallback | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._duration = _duration(duration)
        self.repeat = _boolean(repeat, "repeat")
        self.time_domain = _clock_domain(time_domain)
        if callback is not None and not callable(callback):
            raise TypeError("callback must be callable or None")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.callback = callback
        self._clock = clock
        self._elapsed = 0.0
        self._completions = 0
        self._running = False
        self._finished = False
        self._cancelled = False
        self._wall_mark: float | None = None
        if _boolean(autostart, "autostart"):
            self.start()

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def elapsed(self) -> float:
        return self._elapsed

    @property
    def remaining(self) -> float:
        return max(0.0, self.duration - self._elapsed)

    @property
    def progress(self) -> float:
        return min(1.0, self._elapsed / self.duration)

    @property
    def completions(self) -> int:
        return self._completions

    @property
    def running(self) -> bool:
        return self._running

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def start(self, *, reset: bool = False) -> None:
        if reset or self._finished or self._cancelled:
            self._elapsed = 0.0
            self._finished = False
            self._cancelled = False
            if reset:
                self._completions = 0
        self._running = True
        self._wall_mark = self._read_clock() if self.time_domain is ClockDomain.WALL else None

    def pause(self) -> None:
        self._running = False
        self._wall_mark = None

    def resume(self) -> None:
        if self._finished or self._cancelled:
            raise RuntimeError("cannot resume a finished or cancelled timer; call start")
        self.start()

    def cancel(self) -> None:
        self._running = False
        self._cancelled = True
        self._wall_mark = None

    def reset(self, *, start: bool = False) -> None:
        self._elapsed = 0.0
        self._completions = 0
        self._running = False
        self._finished = False
        self._cancelled = False
        self._wall_mark = None
        if start:
            self.start()

    def advance(
        self,
        delta_seconds: float,
        *,
        time_domain: ClockDomain | str | None = None,
    ) -> int:
        if self.time_domain is ClockDomain.WALL:
            raise RuntimeError("wall timers use poll(), not advance()")
        self._validate_advance_domain(time_domain)
        return self._advance(_delta(delta_seconds))

    def poll(self) -> int:
        if self.time_domain is not ClockDomain.WALL:
            raise RuntimeError("poll() is available only for wall timers")
        if not self._running:
            return 0
        now = self._read_clock()
        mark = self._wall_mark
        self._wall_mark = now
        return self._advance(0.0 if mark is None else _delta(now - mark))

    def _advance(self, delta_seconds: float) -> int:
        if not self._running or delta_seconds == 0:
            return 0
        total = self._elapsed + delta_seconds
        completions = math.floor(total / self.duration + 1.0e-12)
        if completions == 0:
            self._elapsed = total
            return 0
        if not self.repeat:
            completions = 1
        elif completions > self._MAX_CALLBACKS_PER_ADVANCE:
            raise RuntimeError("timer advance exceeds the callback safety limit")

        previous_completions = self._completions
        self._completions += completions
        if self.repeat:
            self._elapsed = max(0.0, total - completions * self.duration)
        else:
            self._elapsed = self.duration
            self._running = False
            self._finished = True

        if self.callback is not None:
            for index in range(completions):
                self._completions = previous_completions + index + 1
                self.callback(self)
                if self._cancelled:
                    break
            self._completions = previous_completions + completions
        return completions

    def _validate_advance_domain(self, value: ClockDomain | str | None) -> None:
        if value is not None and _clock_domain(value) is not self.time_domain:
            raise ValueError(
                f"timer belongs to {self.time_domain.value!r} time, not "
                f"{_clock_domain(value).value!r}"
            )

    def _read_clock(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value):
            raise ValueError("clock returned a non-finite value")
        return value


class Cooldown:
    """One-shot timer that rejects activation until it is ready."""

    def __init__(
        self,
        duration: float,
        *,
        time_domain: ClockDomain | str = ClockDomain.SIMULATION,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._timer = Timer(duration, time_domain=time_domain, clock=clock)

    @property
    def duration(self) -> float:
        return self._timer.duration

    @property
    def time_domain(self) -> ClockDomain:
        return self._timer.time_domain

    @property
    def ready(self) -> bool:
        return not self._timer.running

    @property
    def remaining(self) -> float:
        return self._timer.remaining if self._timer.running else 0.0

    @property
    def progress(self) -> float:
        return self._timer.progress if self._timer.running else 1.0

    def trigger(self, *, restart: bool = False) -> bool:
        if self._timer.running and not restart:
            return False
        self._timer.start(reset=True)
        return True

    def cancel(self) -> None:
        self._timer.cancel()

    def advance(
        self,
        delta_seconds: float,
        *,
        time_domain: ClockDomain | str | None = None,
    ) -> bool:
        return self._timer.advance(delta_seconds, time_domain=time_domain) > 0

    def poll(self) -> bool:
        return self._timer.poll() > 0


@dataclass(frozen=True, slots=True)
class Subscription:
    event: str
    id: int


@dataclass(slots=True)
class _Listener:
    token: Subscription
    callback: Callable[..., Any]
    priority: int
    once: bool


class EventBus:
    """Synchronous event bus with stable priority and subscription ordering."""

    def __init__(self, *, max_dispatch_depth: int = 32) -> None:
        if isinstance(max_dispatch_depth, bool) or not isinstance(max_dispatch_depth, int):
            raise TypeError("max_dispatch_depth must be a positive integer")
        if max_dispatch_depth <= 0:
            raise ValueError("max_dispatch_depth must be a positive integer")
        self.max_dispatch_depth = max_dispatch_depth
        self._listeners: dict[str, dict[int, _Listener]] = {}
        self._next_id = 1
        self._depth = 0

    def subscribe(
        self,
        event: str,
        callback: Callable[..., Any],
        *,
        priority: int = 0,
        once: bool = False,
    ) -> Subscription:
        if not isinstance(event, str) or not event:
            raise ValueError("event must be a non-empty string")
        if not callable(callback):
            raise TypeError("callback must be callable")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise TypeError("priority must be an integer")
        token = Subscription(event, self._next_id)
        self._next_id += 1
        self._listeners.setdefault(event, {})[token.id] = _Listener(
            token, callback, priority, _boolean(once, "once")
        )
        return token

    def unsubscribe(self, token: Subscription) -> bool:
        if not isinstance(token, Subscription):
            raise TypeError("token must be a Subscription")
        listeners = self._listeners.get(token.event)
        if listeners is None or token.id not in listeners:
            return False
        del listeners[token.id]
        if not listeners:
            del self._listeners[token.event]
        return True

    def emit(self, event: str, *args: Any, **kwargs: Any) -> int:
        if not isinstance(event, str) or not event:
            raise ValueError("event must be a non-empty string")
        if self._depth >= self.max_dispatch_depth:
            raise RuntimeError("event dispatch depth limit exceeded")
        snapshot = sorted(
            self._listeners.get(event, {}).values(),
            key=lambda listener: (-listener.priority, listener.token.id),
        )
        called = 0
        self._depth += 1
        try:
            for listener in snapshot:
                current = self._listeners.get(event, {})
                if listener.token.id not in current:
                    continue
                if listener.once:
                    self.unsubscribe(listener.token)
                listener.callback(*args, **kwargs)
                called += 1
        finally:
            self._depth -= 1
        return called

    def clear(self, event: str | None = None) -> None:
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event, None)

    def listener_count(self, event: str | None = None) -> int:
        if event is None:
            return sum(len(listeners) for listeners in self._listeners.values())
        return len(self._listeners.get(event, ()))


TweenValue = TypeVar("TweenValue")
Interpolator = Callable[[TweenValue, TweenValue, float], TweenValue]
EasingFunction = Callable[[float], float]


def _ease(value: Easing | str | EasingFunction) -> EasingFunction:
    if callable(value):
        return value
    try:
        easing = Easing(value)
    except ValueError as error:
        choices = ", ".join(item.value for item in Easing)
        raise ValueError(f"easing must be callable or one of: {choices}") from error
    if easing is Easing.LINEAR:
        return lambda amount: amount
    if easing is Easing.EASE_IN:
        return lambda amount: amount * amount
    if easing is Easing.EASE_OUT:
        return lambda amount: 1.0 - (1.0 - amount) ** 2
    return lambda amount: amount * amount * (3.0 - 2.0 * amount)


def _interpolate(start: Any, end: Any, amount: float) -> Any:
    if isinstance(start, tuple) and isinstance(end, tuple):
        if len(start) != len(end):
            raise ValueError("tuple tween endpoints must have equal length")
        return tuple(_interpolate(a, b, amount) for a, b in zip(start, end))
    return start + (end - start) * amount


class Tween(Generic[TweenValue]):
    """Time-domain-aware interpolation for scalars, vectors, or tuples."""

    def __init__(
        self,
        start: TweenValue,
        end: TweenValue,
        duration: float,
        *,
        easing: Easing | str | EasingFunction = Easing.LINEAR,
        loop: bool = False,
        ping_pong: bool = False,
        autostart: bool = False,
        time_domain: ClockDomain | str = ClockDomain.RENDER,
        interpolate: Interpolator[TweenValue] | None = None,
        on_update: Callable[[TweenValue], None] | None = None,
        on_complete: Callable[[TweenValue], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.start_value = start
        self.end_value = end
        self._duration = _duration(duration)
        self.easing = _ease(easing)
        self.ping_pong = _boolean(ping_pong, "ping_pong")
        self.loop = _boolean(loop, "loop") or self.ping_pong
        self.time_domain = _clock_domain(time_domain)
        if interpolate is not None and not callable(interpolate):
            raise TypeError("interpolate must be callable or None")
        self.interpolate = (
            interpolate
            if interpolate is not None
            else cast(Interpolator[TweenValue], _interpolate)
        )
        if on_update is not None and not callable(on_update):
            raise TypeError("on_update must be callable or None")
        if on_complete is not None and not callable(on_complete):
            raise TypeError("on_complete must be callable or None")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.on_update = on_update
        self.on_complete = on_complete
        self._clock = clock
        self._phase = 0.0
        self._progress = 0.0
        self._value = start
        self._running = False
        self._finished = False
        self._wall_mark: float | None = None
        if _boolean(autostart, "autostart"):
            self.start()

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def value(self) -> TweenValue:
        return self._value

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def running(self) -> bool:
        return self._running

    @property
    def finished(self) -> bool:
        return self._finished

    def start(self, *, reset: bool = False) -> None:
        if reset or self._finished:
            self.reset()
        self._running = True
        self._wall_mark = self._read_clock() if self.time_domain is ClockDomain.WALL else None

    def pause(self) -> None:
        self._running = False
        self._wall_mark = None

    def resume(self) -> None:
        if self._finished:
            raise RuntimeError("cannot resume a finished tween; call start")
        self.start()

    def cancel(self) -> None:
        self._running = False
        self._wall_mark = None

    def reset(self, *, start: bool = False) -> None:
        self._phase = 0.0
        self._progress = 0.0
        self._value = self.start_value
        self._running = False
        self._finished = False
        self._wall_mark = None
        if self.on_update is not None:
            self.on_update(self._value)
        if start:
            self.start()

    def advance(
        self,
        delta_seconds: float,
        *,
        time_domain: ClockDomain | str | None = None,
    ) -> TweenValue:
        if self.time_domain is ClockDomain.WALL:
            raise RuntimeError("wall tweens use poll(), not advance()")
        self._validate_advance_domain(time_domain)
        return self._advance(_delta(delta_seconds))

    def poll(self) -> TweenValue:
        if self.time_domain is not ClockDomain.WALL:
            raise RuntimeError("poll() is available only for wall tweens")
        if not self._running:
            return self._value
        now = self._read_clock()
        mark = self._wall_mark
        self._wall_mark = now
        return self._advance(0.0 if mark is None else _delta(now - mark))

    def _advance(self, delta_seconds: float) -> TweenValue:
        if not self._running or delta_seconds == 0:
            return self._value
        total = self._phase + delta_seconds
        completed = False
        if self.loop:
            period = self.duration * (2.0 if self.ping_pong else 1.0)
            next_phase = math.fmod(total, period)
            if self.ping_pong and next_phase > self.duration:
                linear = 2.0 - next_phase / self.duration
            else:
                linear = next_phase / self.duration
        else:
            next_phase = min(total, self.duration)
            linear = next_phase / self.duration
            completed = next_phase >= self.duration

        eased = float(self.easing(linear))
        if not math.isfinite(eased):
            raise ValueError("easing function returned a non-finite value")
        eased = min(1.0, max(0.0, eased))
        next_value = self.interpolate(self.start_value, self.end_value, eased)
        self._phase = next_phase
        self._progress = linear
        self._value = next_value
        if completed:
            self._running = False
            self._finished = True
        if self.on_update is not None:
            self.on_update(self._value)
        if completed:
            if self.on_complete is not None:
                self.on_complete(self._value)
        return self._value

    def _validate_advance_domain(self, value: ClockDomain | str | None) -> None:
        if value is not None and _clock_domain(value) is not self.time_domain:
            raise ValueError(
                f"tween belongs to {self.time_domain.value!r} time, not "
                f"{_clock_domain(value).value!r}"
            )

    def _read_clock(self) -> float:
        value = float(self._clock())
        if not math.isfinite(value):
            raise ValueError("clock returned a non-finite value")
        return value


__all__ = [
    "AnimationSelection",
    "ClockDomain",
    "Cooldown",
    "Easing",
    "EventBus",
    "State",
    "StateMachine",
    "Subscription",
    "TimedTransition",
    "Timer",
    "Transition",
    "Tween",
]
