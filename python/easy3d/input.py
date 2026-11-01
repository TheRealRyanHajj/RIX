"""Thread-safe input snapshots and remappable action bindings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ._easy3d import _NativeInput


def _name(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    result = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _control(value: str) -> str:
    result = _name(value, "control")
    if ":" not in result:
        raise ValueError("control must use 'key:', 'mouse:', or 'gamepad:'")
    device, control_name = result.split(":", 1)
    if device not in ("key", "mouse", "gamepad") or not control_name:
        raise ValueError("control must use 'key:', 'mouse:', or 'gamepad:'")
    return f"{device}:{control_name}"


@dataclass(frozen=True, slots=True)
class Binding:
    """One physical control contribution to an action."""

    control: str
    scale: float = 1.0
    deadzone: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "control", _control(self.control))
        scale = float(self.scale)
        deadzone = float(self.deadzone)
        if not math.isfinite(scale):
            raise ValueError("binding scale must be finite")
        if not math.isfinite(deadzone) or not 0.0 <= deadzone < 1.0:
            raise ValueError("binding deadzone must be finite and in [0, 1)")
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "deadzone", deadzone)


@dataclass(frozen=True, slots=True)
class ActionState:
    value: float
    down: bool
    pressed: bool
    released: bool


@dataclass(frozen=True, slots=True)
class PointerState:
    position: tuple[float, float]
    delta: tuple[float, float]
    wheel: tuple[float, float]


class Input:
    """A game's physical input snapshot and remappable actions."""

    __slots__ = ("_native",)

    def __init__(self, native: _NativeInput) -> None:
        self._native = native

    def bind(
        self,
        action: str,
        *bindings: str | Binding,
        replace: bool = True,
    ) -> None:
        """Bind controls to an action, replacing its map by default."""

        action_name = _name(action, "action")
        if not bindings:
            raise ValueError("at least one input binding is required")
        normalized = tuple(
            binding if isinstance(binding, Binding) else Binding(binding)
            for binding in bindings
        )
        self._native.bind_action(
            action_name,
            [(item.control, item.scale, item.deadzone) for item in normalized],
            bool(replace),
        )

    def unbind(self, action: str) -> None:
        self._native.unbind_action(_name(action, "action"))

    def clear_actions(self) -> None:
        self._native.clear_actions()

    def state(self, action: str) -> ActionState:
        return ActionState(*self._native.action_state(_name(action, "action")))

    def value(self, action: str) -> float:
        return self.state(action).value

    def down(self, action: str) -> bool:
        return self.state(action).down

    def pressed(self, action: str) -> bool:
        return self.state(action).pressed

    def released(self, action: str) -> bool:
        return self.state(action).released

    def bindings(self, action: str) -> tuple[Binding, ...]:
        return tuple(
            Binding(*value)
            for value in self._native.action_bindings(_name(action, "action"))
        )

    def key_down(self, key: str) -> bool:
        return self._native.control_value(f"key:{_name(key, 'key')}") > 0.5

    def mouse_button_down(self, button: str) -> bool:
        return self._native.control_value(
            f"mouse:{_name(button, 'mouse button')}"
        ) > 0.5

    def gamepad_button_down(self, button: str) -> bool:
        return self._native.control_value(
            f"gamepad:{_name(button, 'gamepad button')}"
        ) > 0.5

    def gamepad_axis(self, axis: str) -> float:
        return float(
            self._native.control_value(f"gamepad:{_name(axis, 'gamepad axis')}")
        )

    @property
    def pointer(self) -> PointerState:
        x, y, delta_x, delta_y, wheel_x, wheel_y = self._native.pointer_state
        return PointerState((x, y), (delta_x, delta_y), (wheel_x, wheel_y))

    @property
    def focused(self) -> bool:
        return bool(self._native.focused)

    @property
    def pointer_lock_requested(self) -> bool:
        return bool(self._native.pointer_lock_requested)

    @pointer_lock_requested.setter
    def pointer_lock_requested(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("pointer_lock_requested must be a bool")
        self._native.pointer_lock_requested = value

    @property
    def pointer_locked(self) -> bool:
        return bool(self._native.pointer_lock_active)

    @property
    def gamepad_connected(self) -> bool:
        return bool(self._native.gamepad_connected)

    @property
    def gamepad_name(self) -> str:
        return str(self._native.gamepad_name)

    def __len__(self) -> int:
        return int(self._native.action_count)
