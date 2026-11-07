"""Timed SDL keyboard/mouse/gamepad and pointer-lock diagnostic."""

from __future__ import annotations

import argparse
import threading
import time

from rix import Binding, Game


def run(*, seconds: float, pointer_lock: bool) -> None:
    game = Game("RIX input diagnostic", (800, 450), vsync=False)
    game.input.bind(
        "move_x",
        Binding("key:d"),
        Binding("key:a", scale=-1),
        Binding("gamepad:left_x", deadzone=0.2),
    )
    game.input.bind("jump", "key:space", "gamepad:a")
    game.input.pointer_lock_requested = pointer_lock
    observed_pointer_lock = False
    observed_focus = False

    def monitor() -> None:
        nonlocal observed_focus, observed_pointer_lock
        while not game.is_running:
            time.sleep(0.001)
        deadline = time.perf_counter() + seconds
        while game.is_running and time.perf_counter() < deadline:
            observed_focus |= game.input.focused
            observed_pointer_lock |= game.input.pointer_locked
            time.sleep(0.005)
        game.stop()

    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    game.run()
    worker.join(timeout=1)
    if pointer_lock and not observed_pointer_lock:
        raise RuntimeError(
            "SDL relative mouse mode never became active "
            f"(window_focus_observed={observed_focus})"
        )
    print(
        "input_diagnostic: PASS "
        f"frames={game.frame_count} focus_observed={observed_focus} "
        f"pointer_lock_observed={observed_pointer_lock} "
        f"gamepad_connected={game.input.gamepad_connected}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--pointer-lock", action="store_true")
    arguments = parser.parse_args()
    if arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(seconds=arguments.seconds, pointer_lock=arguments.pointer_lock)


if __name__ == "__main__":
    main()
