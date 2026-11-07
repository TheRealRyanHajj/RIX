from __future__ import annotations

import pytest

from rix import (
    AnimationSelection,
    Entity,
    Game,
    GameStates,
    ScreenPolicy,
    StateMachine,
)


def test_decorator_states_support_safe_change_from_update() -> None:
    machine = StateMachine("idle")
    calls: list[tuple[str, object]] = []

    @machine.state("idle")
    def idle(dt: float) -> None:
        calls.append(("idle", dt))
        machine.change("chase")

    @machine.state("chase")
    def chase(dt: float) -> None:
        calls.append(("chase", dt))

    @machine.exit("idle")
    def leave_idle(target: str | None) -> None:
        calls.append(("exit", target))

    @machine.enter("chase")
    def enter_chase(previous: str | None) -> None:
        calls.append(("enter", previous))

    machine.update(0.25)
    assert machine.current == "chase"
    assert machine.previous == "idle"
    assert machine.elapsed == 0.0
    assert calls == [
        ("idle", 0.25),
        ("exit", "chase"),
        ("enter", "idle"),
    ]
    machine.update(0.1)
    assert calls[-1] == ("chase", 0.1)


def test_initial_enter_runs_after_all_decorators_are_registered() -> None:
    machine = StateMachine("idle")
    calls: list[str | None] = []

    @machine.state("idle")
    def idle(_dt: float) -> None:
        pass

    @machine.enter("idle")
    def enter(previous: str | None) -> None:
        calls.append(previous)

    assert machine.current is None
    machine.update(0.0)
    assert machine.current == "idle"
    assert calls == [None]


def test_entity_state_machine_can_be_decorated_after_attachment() -> None:
    game = Game("state owner")
    try:
        entity = Entity("actor")
        machine = entity.state_machine("idle")

        @machine.state("idle")
        def idle(_dt: float) -> None:
            pass

        assert entity.states is machine
        assert machine.current is None
        machine.update(0.0)
        assert machine.current == "idle"
    finally:
        game.close()


def test_state_animation_selection_does_not_restart_unchanged_clip() -> None:
    selection = AnimationSelection()
    machine = StateMachine("idle")
    machine.bind_animations(selection)

    @machine.state("idle", animation="idle")
    def idle(_dt: float) -> None:
        pass

    @machine.state("look", animation="idle")
    def look(_dt: float) -> None:
        pass

    @machine.state("run", animation="run")
    def run(_dt: float) -> None:
        pass

    machine.update(0.0)
    assert (selection.current, selection.revision) == ("idle", 1)
    machine.change("look")
    assert (selection.current, selection.revision) == ("idle", 1)
    machine.change("run")
    assert (selection.current, selection.previous, selection.revision) == (
        "run",
        "idle",
        2,
    )
    assert not selection.play("run")
    assert selection.play("run", restart=True)
    assert selection.revision == 3


def test_entity_machine_freezes_disabled_and_cancels_on_destroy() -> None:
    game = Game("state lifecycle")
    try:
        entity = Entity("actor")
        machine = entity.state_machine("idle")
        calls: list[float] = []

        @machine.state("idle")
        def idle(dt: float) -> None:
            calls.append(dt)

        for callback in tuple(game._update_callbacks):
            callback(0.1)
        assert calls == [0.1]
        entity.disable()
        for callback in tuple(game._update_callbacks):
            callback(0.2)
        assert calls == [0.1]
        entity.enable()
        for callback in tuple(game._update_callbacks):
            callback(0.3)
        assert calls == [0.1, 0.3]

        handle = machine._rix_handle
        entity.destroy()
        assert not handle.active
        assert machine.elapsed == pytest.approx(0.4)
    finally:
        game.close()


def test_entity_machine_cancels_on_scene_detach_and_rejects_duplicate() -> None:
    game = Game("state detach")
    scene = game.scene
    assert scene is not None
    entity = Entity("actor")
    machine = entity.state_machine("idle")

    @machine.state("idle")
    def idle(_dt: float) -> None:
        pass

    with pytest.raises(ValueError, match="already has"):
        entity.add_state_machine(StateMachine("other"))
    handle = machine._rix_handle
    assert game.unload_scene() is scene
    assert not handle.active
    game.close()


def test_conditional_priority_timers_pause_and_reset() -> None:
    machine = StateMachine()
    machine.add_state("idle")
    machine.add_state("low")
    machine.add_state("high")
    machine.when("idle", "low", condition=lambda: True, priority=1)
    machine.when("idle", "high", condition=lambda: True, priority=10)
    machine.start("idle")
    machine.update(0)
    assert machine.current == "high"

    machine.reset("idle")
    timer = machine.after(0.5, "low")
    machine.pause()
    machine.update(1)
    assert machine.current == "idle" and timer.elapsed == 0
    machine.resume()
    machine.update(0.5)
    # Higher-priority conditions run after the timer's low transition and no
    # condition is registered from low, so the timed target remains stable.
    assert machine.current == "low"


def test_failed_enter_restores_a_consistent_source_state() -> None:
    machine = StateMachine()
    machine.add_state("safe")
    machine.add_state(
        "broken", on_enter=lambda _previous: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    machine.start("safe")
    with pytest.raises(RuntimeError, match="boom"):
        machine.change("broken")
    assert machine.current == "safe"


def test_game_states_defer_callback_changes_and_draw_overlays_bottom_to_top() -> None:
    manager = GameStates("menu")
    calls: list[str] = []

    @manager.screen("menu")
    class Menu:
        def update(self, dt: float) -> None:
            calls.append(f"menu update {dt}")
            manager.change("playing")

        def draw(self, _surface: object) -> None:
            calls.append("menu draw")

    @manager.screen("playing")
    class Playing:
        def enter(self, previous: str | None) -> None:
            calls.append(f"playing enter {previous}")

        def update(self, _dt: float) -> None:
            calls.append("playing update")
            manager.push("paused")

        def draw(self, _surface: object) -> None:
            calls.append("playing draw")

    @manager.screen("paused")
    class Paused:
        def draw(self, _surface: object) -> None:
            calls.append("paused draw")

    manager.update(0.25)
    assert manager.current == "playing"
    manager.update(0.1)
    assert manager.stack == ("playing", "paused")
    manager.draw(object())
    assert calls[-2:] == ["playing draw", "paused draw"]
    assert manager.pop() == "paused"
    assert manager.current == "playing"


def test_game_state_timer_is_owned_by_current_screen() -> None:
    manager = GameStates("menu")

    @manager.screen("menu")
    class Menu:
        pass

    @manager.screen("game")
    class Game:
        pass

    timer = manager.after(0.2, "game")
    manager.update(0.1)
    assert manager.current == "menu"
    manager.update(0.1)
    assert manager.current == "game"
    assert timer.cancelled


def test_game_state_propagation_policy_has_stable_direction() -> None:
    manager = GameStates("game")
    calls: list[str] = []

    @manager.screen("game")
    class GameScreen:
        def event(self, _event: object) -> None:
            calls.append("game event")

        def update(self, _dt: float) -> None:
            calls.append("game update")

        def fixed_update(self, _dt: float) -> None:
            calls.append("game fixed")

        def draw(self, _surface: object) -> None:
            calls.append("game draw")

    @manager.screen(
        "hud",
        update_underlay=True,
        event_underlay=True,
        draw_underlay=True,
    )
    class Hud:
        def event(self, _event: object) -> None:
            calls.append("hud event")

        def update(self, _dt: float) -> None:
            calls.append("hud update")

        def fixed_update(self, _dt: float) -> None:
            calls.append("hud fixed")

        def draw(self, _surface: object) -> None:
            calls.append("hud draw")

    @manager.screen(
        "modal",
        update_underlay=True,
        event_underlay=True,
        draw_underlay=False,
    )
    class Modal:
        def event(self, _event: object) -> None:
            calls.append("modal event")

        def update(self, _dt: float) -> None:
            calls.append("modal update")

        def fixed_update(self, _dt: float) -> None:
            calls.append("modal fixed")

        def draw(self, _surface: object) -> None:
            calls.append("modal draw")

    manager.push("hud")
    manager.push("modal")
    assert manager.policy("modal") == ScreenPolicy(True, True, False)

    manager.event(object())
    assert calls == ["modal event", "hud event", "game event"]
    calls.clear()
    manager.update(0.1)
    assert calls == ["game update", "hud update", "modal update"]
    calls.clear()
    manager.fixed_update(0.1)
    assert calls == ["game fixed", "hud fixed", "modal fixed"]
    calls.clear()
    manager.draw(object())
    assert calls == ["modal draw"]


def test_game_state_policy_controls_underlay_timers() -> None:
    manager = GameStates("game")

    @manager.screen("game")
    class GameScreen:
        pass

    @manager.screen("pause")
    class Pause:
        pass

    @manager.screen("non_blocking", update_underlay=True)
    class NonBlocking:
        pass

    paused_timer = manager.after(0.2, "pause", screen="game")
    manager.push("pause")
    manager.update(0.2)
    assert paused_timer.elapsed == 0
    manager.pop()
    manager.push("non_blocking")
    manager.update(0.2)
    assert paused_timer.cancelled
    assert manager.current == "pause"


def test_game_states_owns_one_instance_and_closes_deterministically() -> None:
    manager = GameStates("menu")

    class Shared:
        pass

    manager.screen("menu")(Shared)
    with pytest.raises(ValueError, match="already registered as"):
        manager.screen("duplicate")(Shared)
    assert manager.registered == ("menu",)
    assert manager.get("menu") is manager.get("menu") is manager.screen_object

    manager.close()
    manager.close()
    assert manager.closed and manager.stack == ()
    with pytest.raises(RuntimeError, match="closed"):
        manager.update(0.1)
    with pytest.raises(RuntimeError, match="closed"):
        manager.screen("late")


def test_game_state_policy_rejects_non_boolean_options() -> None:
    manager = GameStates("menu")
    with pytest.raises(TypeError, match="bools"):
        manager.screen("menu", update_underlay=1)  # type: ignore[arg-type]
