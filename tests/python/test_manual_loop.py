from __future__ import annotations

from collections.abc import Callable

import pytest

from rix import Cube, Game, ScriptCallbackError


class _FakeEngine:
    """Deterministic native-loop seam; renderer integration lives in tests/manual."""

    def __init__(self, frame_seconds: float = 1.0 / 60.0) -> None:
        self.frame_seconds = frame_seconds
        self.is_running = False
        self.frame_count = 0
        self.last_frame_seconds = 0.0
        self.viewport_size = (640, 480)
        self.limits: list[float] = []
        self.stopped = False
        self.scene = None

    def tick(self, callback: Callable[[float], None], fps_limit: float) -> float:
        if self.stopped:
            self.is_running = False
            return self.last_frame_seconds
        self.is_running = True
        self.last_frame_seconds = self.frame_seconds
        self.limits.append(fps_limit)
        callback(self.frame_seconds)
        self.frame_count += 1
        if self.stopped:
            self.is_running = False
        return self.frame_seconds

    def run(self, _callback: Callable[[float], None]) -> None:
        raise AssertionError("managed native run should not be entered in this test")

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.is_running = False

    def set_scene(self, scene: object) -> None:
        self.scene = scene


def _manual_game() -> tuple[Game, _FakeEngine]:
    game = Game("manual test")
    engine = _FakeEngine()
    game._engine = engine  # type: ignore[assignment]
    return game, engine


def test_manual_tick_uses_managed_scheduler_once_and_passes_frame_limit() -> None:
    game, engine = _manual_game()
    cube = Cube()
    updates: list[float] = []
    fixed: list[float] = []
    game.on_update(updates.append)
    game.on_fixed_update(fixed.append)

    assert game.running and not game.is_running
    first = game.tick(120)
    cube.ry += 15
    second = game.tick()

    assert first == second == pytest.approx(1.0 / 60.0)
    assert engine.limits == [120.0, -1.0]
    assert engine.frame_count == 2
    assert len(updates) == len(fixed) == 2
    assert game.scheduler_stats.fixed_ticks == 2
    assert cube.is_alive
    assert cube.ry == pytest.approx(15)
    game.close()
    assert not game.running and game.scene is None


def test_stop_ends_manual_loop_and_context_manager_closes_session() -> None:
    game, engine = _manual_game()
    with game:
        game.tick(0)
        assert engine.is_running
        game.stop()
        assert not game.running
    assert not engine.is_running
    assert game.scene is None


def test_manual_loop_rejects_managed_run_recursive_tick_and_bad_limits() -> None:
    game, _engine = _manual_game()
    game.tick()
    with pytest.raises(RuntimeError, match="manual loop"):
        game.run()
    game._inside_tick = True
    with pytest.raises(RuntimeError, match="recursive"):
        game.tick()
    game._inside_tick = False
    with pytest.raises(TypeError, match="fps"):
        game.tick(True)
    with pytest.raises(ValueError, match="fps"):
        game.tick(-1)
    game.close()


def test_manual_callback_exception_preserves_python_cause_and_closes_loop() -> None:
    game, engine = _manual_game()

    @game.update
    def fail(_dt: float) -> None:
        raise ValueError("gameplay exploded")

    with pytest.raises(ScriptCallbackError) as captured:
        game.tick()
    assert isinstance(captured.value.__cause__, ValueError)
    assert "gameplay exploded" in str(captured.value.__cause__)
    assert not engine.is_running
    assert not game.running
    game.close()

