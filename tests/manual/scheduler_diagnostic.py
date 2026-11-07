"""Live Python callback, exception, and native-loop recovery diagnostic."""

from __future__ import annotations

import threading
import time

from rix import Entity, Game, Scene, ScriptCallbackError


class BrokenScript(Entity):
    def update(self, dt: float) -> None:
        del dt
        raise ValueError("intentional scheduler diagnostic failure")


def main() -> None:
    fail_fast_scene = Scene("fail-fast scheduler")
    BrokenScript("fail-fast actor", scene=fail_fast_scene)
    fail_fast_game = Game("RIX scheduler fail-fast", fail_fast=True)
    fail_fast_game.load_scene(fail_fast_scene)
    try:
        fail_fast_game.run()
    except ScriptCallbackError as error:
        if "fail-fast actor" not in str(error):
            raise
    else:
        raise RuntimeError("fail-fast callback error did not propagate")
    if fail_fast_game.is_running:
        raise RuntimeError("engine remained running after callback failure")

    tolerant_scene = Scene("tolerant scheduler")
    BrokenScript("tolerant actor", scene=tolerant_scene)
    tolerant_game = Game("RIX scheduler tolerant", fail_fast=False)
    tolerant_game.load_scene(tolerant_scene)

    def stop_later() -> None:
        time.sleep(0.5)
        tolerant_game.stop()

    threading.Thread(target=stop_later, daemon=True).start()
    tolerant_game.run()
    if len(tolerant_game.script_errors) != 1:
        raise RuntimeError("tolerant scheduler did not quarantine exactly one failure")
    print(
        "scheduler_diagnostic: PASS "
        f"frames={tolerant_game.frame_count} errors={len(tolerant_game.script_errors)}"
    )


if __name__ == "__main__":
    main()
