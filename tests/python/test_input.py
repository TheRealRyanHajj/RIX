from __future__ import annotations

import math

import pytest

from easy3d import ActionState, Binding, Game, PointerState


def test_game_input_binds_and_remaps_actions() -> None:
    input_state = Game("input test").input
    input_state.bind(
        "move_x",
        Binding("key:d"),
        Binding("key:a", scale=-1),
        Binding("gamepad:left_x", deadzone=0.2),
    )
    assert input_state.state("move_x") == ActionState(0.0, False, False, False)
    bindings = input_state.bindings("move_x")
    assert tuple(binding.control for binding in bindings) == (
        "key:d",
        "key:a",
        "gamepad:left_x",
    )
    assert tuple(binding.scale for binding in bindings) == pytest.approx((1, -1, 1))
    assert tuple(binding.deadzone for binding in bindings) == pytest.approx((0, 0, 0.2))

    input_state.bind("move_x", "key:right", replace=True)
    assert input_state.bindings("move_x") == (Binding("key:right"),)
    input_state.bind("move_x", "key:left", replace=False)
    assert len(input_state.bindings("move_x")) == 2
    assert len(input_state) == 1
    input_state.unbind("move_x")
    assert len(input_state) == 0


def test_input_raw_defaults_and_pointer_lock_request() -> None:
    input_state = Game("input defaults").input
    assert input_state.focused
    assert not input_state.key_down("space")
    assert not input_state.mouse_button_down("left")
    assert not input_state.gamepad_button_down("a")
    assert input_state.gamepad_axis("left_x") == 0.0
    assert input_state.pointer == PointerState((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    assert not input_state.pointer_locked

    input_state.pointer_lock_requested = True
    assert input_state.pointer_lock_requested
    assert not input_state.pointer_locked
    with pytest.raises(TypeError):
        input_state.pointer_lock_requested = 1  # type: ignore[assignment]


@pytest.mark.parametrize(
    "binding",
    [
        lambda: Binding("missing-prefix"),
        lambda: Binding("touch:tap"),
        lambda: Binding("key:w", scale=math.nan),
        lambda: Binding("gamepad:left_x", deadzone=1.0),
    ],
)
def test_invalid_bindings_are_rejected(binding: object) -> None:
    with pytest.raises(ValueError):
        binding()  # type: ignore[operator]


def test_missing_action_and_empty_binding_are_rejected() -> None:
    input_state = Game().input
    with pytest.raises(ValueError):
        input_state.bind("jump")
    with pytest.raises(IndexError, match="not bound"):
        input_state.state("jump")
