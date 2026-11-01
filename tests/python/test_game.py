from __future__ import annotations

import math

import pytest

from easy3d import Game, RendererStats


def test_game_construction_does_not_initialize_graphics() -> None:
    game = Game("Unit Test", (640, 480), vsync=False, fps_limit=120)
    assert not game.is_running
    assert game.frame_count == 0
    assert game.last_frame_seconds == 0.0
    assert game.renderer_stats == RendererStats()
    game.stop()


@pytest.mark.parametrize(
    "resolution",
    [(0, 480), (640, 0), (-1, 480), (65_536, 480)],
)
def test_game_rejects_invalid_resolution(resolution: tuple[int, int]) -> None:
    with pytest.raises(ValueError):
        Game(resolution=resolution)


@pytest.mark.parametrize("resolution", [[640, 480], (640.0, 480), (True, 480)])
def test_game_rejects_malformed_resolution(resolution: object) -> None:
    with pytest.raises(TypeError):
        Game(resolution=resolution)  # type: ignore[arg-type]


def test_game_rejects_invalid_fps_limit() -> None:
    with pytest.raises(ValueError):
        Game(fps_limit=-1)
    with pytest.raises(TypeError):
        Game(fps_limit=True)
    with pytest.raises(ValueError):
        Game(fps_limit=math.nan)

