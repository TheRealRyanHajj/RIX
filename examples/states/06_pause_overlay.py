"""Illustrates state-management pattern: 06 Pause Overlay.

Run from the repository root with `python examples/states/06_pause_overlay.py`. See
`examples/states/README.md` for the state-example index."""

from rix import GameStates

screens = GameStates("playing")


@screens.screen("playing")
class Playing:
    def draw(self, _surface: object) -> None:
        print("draw game")


@screens.screen(
    "paused",
    update_underlay=False,
    event_underlay=False,
    draw_underlay=True,
)
class Paused:
    def draw(self, _surface: object) -> None:
        print("draw translucent pause overlay")


screens.push("paused")
screens.draw(object())  # draws playing, then paused
screens.pop()
