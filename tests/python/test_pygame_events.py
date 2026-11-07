from __future__ import annotations

import pygame

import rix


def _adapter_without_window() -> rix.World:
    world = rix.World.__new__(rix.World)
    world._pygame = pygame  # type: ignore[attr-defined]
    world._game = rix.Game(auto_setup=False)  # type: ignore[attr-defined]
    world._screen = None  # type: ignore[attr-defined]
    world._native_window = 1  # type: ignore[attr-defined]
    world._closed = False  # type: ignore[attr-defined]
    world._running = True  # type: ignore[attr-defined]
    world._paused = False  # type: ignore[attr-defined]
    world._pointer_grabbed = False  # type: ignore[attr-defined]
    world._sessions = {}  # type: ignore[attr-defined]
    world.input._native._begin_frame()
    return world


def test_keyboard_mouse_wheel_focus_and_quit_forwarding() -> None:
    world = _adapter_without_window()
    assert world.handle_event(
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, repeat=False)
    )
    assert world.handle_event(
        pygame.event.Event(
            pygame.MOUSEMOTION, pos=(12, 34), rel=(3, -2), buttons=(0, 0, 0)
        )
    )
    assert world.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=-1, y=2))
    world.input._native._end_frame()
    assert world.input.key_down("tab")
    assert world.input.key_pressed("tab")
    assert world.input.pointer.position == (12.0, 34.0)
    assert world.input.pointer.delta == (3.0, -2.0)
    assert world.input.pointer.wheel == (-1.0, 2.0)

    focus_lost = getattr(pygame, "WINDOWFOCUSLOST")
    assert world.handle_event(pygame.event.Event(focus_lost))
    assert not world.input.focused
    assert not world.input.key_down("tab")
    assert world.handle_event(pygame.event.Event(pygame.QUIT))
    assert not world.running
    world.game.close()


def test_unknown_event_is_not_claimed() -> None:
    world = _adapter_without_window()
    custom_type = pygame.event.custom_type()
    assert not world.handle_event(pygame.event.Event(custom_type))
    world.game.close()


def test_standard_controller_names_feed_player_bindings() -> None:
    world = _adapter_without_window()
    world.input.bind("jump", "gamepad:a")
    world.input.bind("move_x", "gamepad:left_x")
    world.handle_event(
        pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=pygame.CONTROLLER_BUTTON_A)
    )
    world.handle_event(
        pygame.event.Event(
            pygame.CONTROLLERAXISMOTION,
            axis=pygame.CONTROLLER_AXIS_LEFTX,
            value=0.75,
        )
    )
    world.input._native._end_frame()
    assert world.input.pressed("jump")
    assert world.input.value("move_x") == 0.75
    world.game.close()


def test_attached_session_is_pumped_even_while_world_is_paused(monkeypatch) -> None:
    world = _adapter_without_window()
    session = rix.net.Session()
    updates: list[float] = []

    def update(_session: rix.net.Session, delta: float = 0.0) -> int:
        updates.append(delta)
        return 0

    monkeypatch.setattr(rix.net.Session, "update", update)
    assert world.attach_session(session) is session
    assert world.sessions == (session,)
    world.pause()
    world.update(0.125)
    assert updates == [0.125]
    assert world.detach_session(session)
    assert not world.detach_session(session)
    world.game.close()


def test_world_closes_only_sessions_with_owned_lifetime(monkeypatch) -> None:
    world = _adapter_without_window()
    owned = rix.net.Session()
    external = rix.net.Session()
    closed: list[tuple[rix.net.Session, str]] = []

    def close(session: rix.net.Session, reason: str = "session closed") -> None:
        closed.append((session, reason))

    monkeypatch.setattr(rix.net.Session, "close", close)
    world.attach_session(owned)
    world.attach_session(external, close_with_world=False)
    world.close()
    assert closed == [(owned, "owning World closed")]
    assert world.sessions == ()

