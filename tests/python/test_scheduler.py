from __future__ import annotations

import threading

import pytest

from easy3d import Cube, Entity, Game, Scene, ScriptCallbackError


def _advance(game: Game, seconds: float) -> None:
    game._gameplay_thread_id = threading.get_ident()
    game._callback_active = True
    try:
        game._scheduler.advance(game.scene, seconds)
    finally:
        game._callback_active = False


def test_lifecycle_order_fixed_tick_and_profiling() -> None:
    events: list[tuple[str, float | None]] = []

    class Actor(Entity):
        def awake(self) -> None:
            events.append(("awake", None))

        def start(self) -> None:
            events.append(("start", None))

        def fixed_update(self, dt: float) -> None:
            events.append(("fixed", dt))

        def update(self, dt: float) -> None:
            events.append(("update", dt))

        def late_update(self, dt: float) -> None:
            events.append(("late", dt))

    game = Game(fixed_hz=60)
    scene = Scene()
    actor = Actor(scene=scene)
    game.load_scene(scene)
    game._scheduler.begin_run()
    _advance(game, 1 / 30)

    assert [name for name, _ in events] == [
        "awake", "start", "fixed", "fixed", "update", "late"
    ]
    assert events[2][1] == pytest.approx(1 / 60)
    assert game.scheduler_stats.fixed_ticks == 2
    assert game.scheduler_stats.callbacks["fixed_update"].calls == 2

    events.clear()
    actor.enabled = False
    _advance(game, 1 / 60)
    assert events == []
    actor.enabled = True
    _advance(game, 1 / 60)
    assert [name for name, _ in events] == ["fixed", "update", "late"]


def test_destroy_is_deferred_until_callback_boundary() -> None:
    events: list[str] = []

    class Disposable(Entity):
        def update(self, dt: float) -> None:
            del dt
            events.append("update")
            self.destroy()
            assert self.is_alive

        def late_update(self, dt: float) -> None:
            del dt
            events.append("late")

        def on_destroy(self) -> None:
            events.append("destroy")

    game = Game()
    scene = Scene()
    actor = Disposable(scene=scene)
    game.load_scene(scene)
    game._scheduler.begin_run()
    _advance(game, 1 / 120)

    assert events == ["update", "destroy"]
    assert not actor.is_alive
    assert scene.entity_count == 0


def test_disabled_script_awakes_but_starts_only_on_first_activation() -> None:
    events: list[str] = []

    class Dormant(Entity):
        def awake(self) -> None:
            events.append("awake")

        def start(self) -> None:
            events.append("start")

        def update(self, dt: float) -> None:
            del dt
            events.append("update")

    game = Game()
    scene = Scene()
    actor = Dormant(scene=scene)
    actor.enabled = False
    game.load_scene(scene)
    game._scheduler.begin_run()
    _advance(game, 0.01)
    assert events == ["awake"]

    actor.enabled = True
    _advance(game, 0.01)
    actor.enabled = False
    _advance(game, 0.01)
    actor.enabled = True
    _advance(game, 0.01)
    assert events == ["awake", "start", "update", "update"]


def test_fail_fast_wraps_identity_and_non_fail_fast_quarantines() -> None:
    class Broken(Entity):
        calls = 0

        def update(self, dt: float) -> None:
            del dt
            self.calls += 1
            raise ValueError("boom")

    fail_fast = Game(fail_fast=True)
    first_scene = Scene()
    Broken("fail fast actor", scene=first_scene)
    fail_fast.load_scene(first_scene)
    fail_fast._scheduler.begin_run()
    with pytest.raises(ScriptCallbackError, match="fail fast actor"):
        _advance(fail_fast, 0.01)

    tolerant = Game(fail_fast=False)
    second_scene = Scene()
    actor = Broken("tolerant actor", scene=second_scene)
    tolerant.load_scene(second_scene)
    tolerant._scheduler.begin_run()
    _advance(tolerant, 0.01)
    _advance(tolerant, 0.01)
    assert actor.calls == 1
    assert len(tolerant.script_errors) == 1
    assert "tolerant actor" in tolerant.script_errors[0]


def test_catch_up_cap_records_dropped_time() -> None:
    game = Game(fixed_hz=60, max_frame_seconds=0.25, max_catch_up_steps=3)
    scene = Scene()

    class Counter(Entity):
        def fixed_update(self, dt: float) -> None:
            del dt

    Counter(scene=scene)
    game.load_scene(scene)
    game._scheduler.begin_run()
    _advance(game, 1.0)
    stats = game.scheduler_stats
    assert stats.fixed_ticks == 3
    assert stats.overrun_count == 1
    assert stats.dropped_seconds == pytest.approx(0.2)


def test_failed_primitive_construction_does_not_run_destroy_hook() -> None:
    destroyed = 0

    class BrokenCube(Cube):
        def on_destroy(self) -> None:
            nonlocal destroyed
            destroyed += 1

    scene = Scene()
    with pytest.raises((TypeError, ValueError)):
        BrokenCube(scene=scene, position=(1.0, 2.0))

    assert destroyed == 0
    assert scene.entity_count == 0


def test_unload_with_clear_runs_destroy_before_detaching_scheduler() -> None:
    events: list[str] = []

    class Actor(Entity):
        def awake(self) -> None:
            events.append("awake")

        def on_destroy(self) -> None:
            events.append("destroy")

    game = Game()
    scene = Scene()
    actor = Actor(scene=scene)
    game.load_scene(scene)
    game._scheduler.begin_run()
    _advance(game, 0.01)

    assert game.unload_scene(clear=True) is scene
    assert events == ["awake", "destroy"]
    assert not actor.is_alive
    assert not game._scheduler._lifecycle
