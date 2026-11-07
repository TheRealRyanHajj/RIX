from __future__ import annotations

import math

import pytest

from rix import (
    ClockDomain,
    Cooldown,
    Cube,
    EventBus,
    Game,
    StateMachine,
    Timer,
    Tween,
)


def test_game_manages_timer_state_machine_and_entity_tween_once() -> None:
    game = Game()
    fired: list[str] = []
    timer = Timer(0.05, callback=lambda _timer: fired.append("timer"))
    timer_handle = game.manage_timer(timer)

    machine = StateMachine()
    machine.add_state("active")
    machine.start("active")
    actor = Cube()
    actor.add_state_machine(machine)
    tween = actor.animate("y", to=2, duration=0.2)
    with pytest.raises(ValueError, match="already managed"):
        game.manage_timer(timer)
    with pytest.raises(ValueError, match="animatable"):
        actor.animate("name", to=2, duration=0.2)

    game._scheduler.begin_run()
    game._scheduler.advance(game.scene, 0.1)
    assert fired == ["timer"]
    assert not timer_handle.active
    assert machine.time_in_state == pytest.approx(0.1)
    assert actor.y == pytest.approx(1.0)
    game._scheduler.advance(game.scene, 0.1)
    assert actor.y == pytest.approx(2.0)
    assert tween.finished

    actor.destroy()
    game.close()


def test_state_machine_lifecycle_event_guard_and_time_accounting() -> None:
    events: list[object] = []
    allow_run = False
    machine = StateMachine()
    machine.add_state(
        "idle",
        on_enter=lambda previous: events.append(("enter idle", previous)),
        on_update=lambda dt: events.append(("update idle", dt)),
        on_exit=lambda target: events.append(("exit idle", target)),
    )
    machine.add_state(
        "run",
        on_enter=lambda previous: events.append(("enter run", previous)),
        on_exit=lambda target: events.append(("exit run", target)),
    )
    machine.add_transition("idle", "run", "move", guard=lambda: allow_run)
    machine.add_transition("run", "idle", "stop")

    machine.start("idle")
    machine.update(0.25)
    assert machine.time_in_state == pytest.approx(0.25)
    assert not machine.trigger("move")
    allow_run = True
    assert machine.trigger("move")
    assert machine.current == "run"
    assert machine.previous == "idle"
    assert machine.time_in_state == 0
    assert machine.trigger("stop")
    machine.stop()
    assert machine.current is None
    assert events == [
        ("enter idle", None),
        ("update idle", 0.25),
        ("exit idle", "run"),
        ("enter run", "idle"),
        ("exit run", "idle"),
        ("enter idle", "run"),
        ("exit idle", None),
    ]


def test_state_machine_validates_transitions_and_rejects_reentrancy() -> None:
    machine = StateMachine()

    def nested(_: float) -> None:
        machine.transition_to("other")

    machine.add_state("active", on_update=nested)
    machine.add_state("other")
    with pytest.raises(KeyError, match="unknown state"):
        machine.add_transition("missing", "other", "go")
    machine.start("active")
    with pytest.raises(RuntimeError, match="reentrant"):
        machine.update(0.1)
    assert machine.current == "active"


def test_timer_one_shot_repeat_pause_and_explicit_domain() -> None:
    fired: list[int] = []
    timer = Timer(
        0.1,
        repeat=True,
        autostart=True,
        time_domain="simulation",
        callback=lambda value: fired.append(value.completions),
    )
    assert timer.advance(0.25, time_domain=ClockDomain.SIMULATION) == 2
    assert timer.elapsed == pytest.approx(0.05)
    assert timer.completions == 2
    assert fired == [1, 2]
    timer.pause()
    assert timer.advance(1.0) == 0
    timer.resume()
    assert timer.advance(0.05) == 1
    with pytest.raises(ValueError, match="belongs to"):
        timer.advance(0.01, time_domain="render")

    one_shot = Timer(1.0, autostart=True)
    assert one_shot.advance(1.5) == 1
    assert one_shot.finished
    assert one_shot.remaining == 0


def test_wall_timer_uses_injected_clock_and_excludes_paused_time() -> None:
    now = 10.0
    timer = Timer(2.0, autostart=True, time_domain="wall", clock=lambda: now)
    now = 10.5
    assert timer.poll() == 0
    timer.pause()
    now = 100.0
    timer.resume()
    now = 101.5
    assert timer.poll() == 1
    assert timer.finished
    with pytest.raises(RuntimeError, match=r"poll\(\)"):
        timer.advance(1.0)


def test_cooldown_activation_restart_and_completion() -> None:
    cooldown = Cooldown(1.0, time_domain="simulation")
    assert cooldown.ready
    assert cooldown.trigger()
    assert not cooldown.trigger()
    assert cooldown.advance(0.4, time_domain="simulation") is False
    assert cooldown.remaining == pytest.approx(0.6)
    assert cooldown.trigger(restart=True)
    assert cooldown.advance(1.0)
    assert cooldown.ready


def test_event_bus_priority_once_and_safe_unsubscribe_during_emit() -> None:
    bus = EventBus()
    calls: list[str] = []
    low = bus.subscribe("hit", lambda: calls.append("low"), priority=-1)

    def remove_low() -> None:
        calls.append("high")
        bus.unsubscribe(low)

    bus.subscribe("hit", remove_low, priority=10, once=True)
    bus.subscribe("hit", lambda: calls.append("middle"))
    assert bus.emit("hit") == 2
    assert calls == ["high", "middle"]
    assert bus.emit("hit") == 1
    assert calls == ["high", "middle", "middle"]
    assert bus.listener_count("hit") == 1


def test_event_bus_bounds_recursive_dispatch() -> None:
    bus = EventBus(max_dispatch_depth=2)
    bus.subscribe("again", lambda: bus.emit("again"))
    with pytest.raises(RuntimeError, match="depth limit"):
        bus.emit("again")


def test_tween_scalar_tuple_easing_completion_and_domain() -> None:
    updates: list[float] = []
    completed: list[float] = []
    tween = Tween(
        0.0,
        10.0,
        2.0,
        easing="ease_in",
        autostart=True,
        time_domain="render",
        on_update=updates.append,
        on_complete=completed.append,
    )
    assert tween.advance(1.0, time_domain="render") == pytest.approx(2.5)
    assert tween.progress == pytest.approx(0.5)
    assert tween.advance(1.0) == pytest.approx(10.0)
    assert tween.finished
    assert completed == [pytest.approx(10.0)]
    with pytest.raises(ValueError, match="belongs to"):
        Tween(0, 1, 1, autostart=True).advance(0.1, time_domain="simulation")

    tuple_tween = Tween((0.0, 2.0), (10.0, 6.0), 1.0, autostart=True)
    assert tuple_tween.advance(0.5) == pytest.approx((5.0, 4.0))


def test_ping_pong_tween_and_wall_tween() -> None:
    tween = Tween(0.0, 1.0, 1.0, ping_pong=True, autostart=True)
    assert tween.advance(1.0) == pytest.approx(1.0)
    assert tween.advance(0.5) == pytest.approx(0.5)
    assert tween.advance(0.5) == pytest.approx(0.0)

    now = 5.0
    wall = Tween(0.0, 8.0, 2.0, autostart=True, time_domain="wall", clock=lambda: now)
    now = 6.0
    assert wall.poll() == pytest.approx(4.0)
    with pytest.raises(RuntimeError, match=r"poll\(\)"):
        wall.advance(0.1)


def test_tween_validation_failure_does_not_partially_advance() -> None:
    tween = Tween(0.0, 1.0, 1.0, easing=lambda _: math.nan, autostart=True)
    with pytest.raises(ValueError, match="non-finite"):
        tween.advance(0.5)
    assert tween.value == 0.0
    assert tween.progress == 0.0
    assert tween.running
