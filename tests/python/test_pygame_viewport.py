from __future__ import annotations

from types import SimpleNamespace

import pygame
import pytest

from rix import Camera, Viewport, World


def fake_world(camera: Camera | None = None) -> World:
    world = object.__new__(World)
    world._game = SimpleNamespace(
        camera=Camera() if camera is None else camera,
        _engine=SimpleNamespace(viewport_size=(320, 200)),
    )
    world._pygame = pygame
    world._screen = None
    world._native_window = 1
    world._closed = False
    world._running = True
    world._paused = False
    world._pointer_grabbed = False
    world._overlay_texture = None
    world._overlay_id = None
    world._mode = "surface"
    return world


def colored_surface(size: tuple[int, int], color: str) -> pygame.Surface:
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(color)
    return surface


def test_viewport_owns_an_independent_camera_snapshot() -> None:
    world_camera = Camera(position=(1, 2, 3), rotation=(4, 5, 6))
    world = fake_world(world_camera)
    viewport = Viewport(world, rect=pygame.Rect(10, 20, 64, 48))
    try:
        assert viewport.rect == pygame.Rect(10, 20, 64, 48)
        assert viewport.camera is not world_camera
        assert viewport.camera.position == world_camera.position
        world_camera.position = (9, 8, 7)
        assert tuple(viewport.camera.position) == (1, 2, 3)
        viewport.camera.position = (-2, 1, 4)
        assert tuple(world_camera.position) == (9, 8, 7)
    finally:
        viewport.close()


def test_viewport_default_refresh_blocks_once_then_buffers(monkeypatch) -> None:
    world = fake_world()
    calls: list[tuple[object, ...]] = []
    poll_results: list[pygame.Surface | None] = [None, colored_surface((40, 30), "green")]

    def render(_world, camera, size):
        calls.append(("render", camera.position, size))
        return colored_surface(size, "red")

    def request(_world, camera, size):
        calls.append(("request", camera.position, size))
        return 41

    def poll(_world, request_id, size):
        calls.append(("poll", request_id, size))
        return poll_results.pop(0)

    monkeypatch.setattr(World, "_render_viewport", render)
    monkeypatch.setattr(World, "_request_viewport", request)
    monkeypatch.setattr(World, "_poll_viewport", poll)
    monkeypatch.setattr(World, "_cancel_viewport", lambda *_args: None)

    viewport = Viewport(world, size=(40, 30))
    try:
        first = viewport.to_surface()
        assert first.get_at((0, 0)) == pygame.Color("red")
        assert [call[0] for call in calls] == ["render"]

        assert viewport.to_surface() is first
        assert [call[0] for call in calls] == ["render", "request"]

        assert viewport.to_surface() is first
        assert [call[0] for call in calls][-1] == "poll"

        completed = viewport.to_surface()
        assert completed is not first
        assert completed.get_at((0, 0)) == pygame.Color("green")
        assert [call[0] for call in calls][-2:] == ["poll", "request"]
    finally:
        viewport.close()


def test_viewport_blocking_wait_consumes_pending_without_double_render(monkeypatch) -> None:
    world = fake_world()
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        World,
        "_request_viewport",
        lambda _world, _camera, size: calls.append(("request", size)) or 7,
    )
    monkeypatch.setattr(
        World,
        "_wait_viewport",
        lambda _world, request_id, size: calls.append(("wait", request_id, size))
        or colored_surface(size, "blue"),
    )
    monkeypatch.setattr(
        World,
        "_render_viewport",
        lambda *_args: calls.append(("unexpected_render",))
        or colored_surface((24, 16), "red"),
    )
    monkeypatch.setattr(
        World,
        "_cancel_viewport",
        lambda _world, request_id: calls.append(("cancel", request_id)),
    )

    viewport = Viewport(world, size=(24, 16))
    placeholder = viewport.refresh(blocking=False)
    assert placeholder.get_size() == (24, 16)
    image = viewport.refresh(blocking=True)
    assert image.get_at((0, 0)) == pygame.Color("blue")
    assert [call[0] for call in calls] == ["request", "wait"]
    viewport.close()
    viewport.close()
    with pytest.raises(RuntimeError, match="closed"):
        viewport.refresh()


def test_viewport_validates_camera_size_and_rect() -> None:
    world = fake_world()
    with pytest.raises(TypeError, match="camera"):
        Viewport(world, size=(10, 10), camera=object())
    with pytest.raises(ValueError, match="mutually exclusive"):
        Viewport(world, size=(10, 10), rect=(0, 0, 10, 10))
    with pytest.raises(ValueError, match="positive"):
        Viewport(world, size=(0, 10))
    with pytest.raises(TypeError, match="integers"):
        Viewport(world, size=(10.0, 10))
