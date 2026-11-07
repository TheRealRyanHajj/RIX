from __future__ import annotations

import pytest

from rix import (
    Button,
    Column,
    Entity,
    Game,
    Grid,
    Health,
    HealthBar,
    Panel,
    ProgressBar,
    Row,
    Scoreboard,
    ScoreboardPanel,
    Text,
)


def test_contextual_row_column_and_nested_layouts_adopt_children() -> None:
    game = Game()
    with Column(x=20, y=20, anchor="top_left", gap=6, padding=4) as column:
        title = Text("Menu")
        with Row(gap=10) as buttons:
            play = Button("Play")
            quit_button = Button("Quit")

    assert column.elements == [title, buttons]
    assert buttons.elements == [play, quit_button]
    assert play.position[0] < quit_button.position[0]
    assert title.position[1] < play.position[1]
    before = quit_button.position
    play.size = (240, 48)
    column.relayout()
    assert quit_button.position[0] > before[0]
    game.close()


def test_grid_uses_largest_cell_dimensions_and_anchor_positions() -> None:
    game = Game()
    with Grid(2, x=0, y=0, anchor="center", gap=5, padding=3) as grid:
        first = Panel(width=100, height=20)
        second = Panel(width=40, height=30)
        third = Panel(width=60, height=10)
    assert len(grid.elements) == 3
    assert first._rect((1280, 720))[1] == second._rect((1280, 720))[1]
    assert second.position[0] > first.position[0]
    assert third._rect((1280, 720))[1] > first._rect((1280, 720))[1]
    assert grid.size == pytest.approx((151, 51))
    game.close()


def test_progress_health_and_scoreboard_views_bind_native_elements() -> None:
    game = Game()
    progress = ProgressBar(0.5, width=200, height=20)
    assert progress.fill.size == pytest.approx((100, 20))
    progress.value = 0.25
    assert progress.fill.size == pytest.approx((50, 20))

    actor = Entity("actor")
    health = Health(actor, 100)
    bar = HealthBar(health, width=160, height=16)
    health.damage(25)
    assert bar.value == pytest.approx(0.75)
    assert bar.fill.size == pytest.approx((120, 16))

    scores = Scoreboard()
    panel = ScoreboardPanel(scores)
    scores.add_player("Ada", score=2)
    scores.add_player("Lin", score=4)
    assert "Lin: 4" in panel.label.text and "Ada: 2" in panel.label.text
    assert panel.label.text.index("Lin") < panel.label.text.index("Ada")
    game.close()
