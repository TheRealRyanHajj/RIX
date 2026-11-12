"""Illustrates state-management pattern: 05 Game Screens.

Run from the repository root with `python examples/states/05_game_screens.py`. See
`examples/states/README.md` for the state-example index."""

from rix import GameStates

screens = GameStates("menu")


@screens.screen("menu")
class Menu:
    def update(self, _dt: float) -> None:
        print("menu -> playing")
        screens.change("playing")


@screens.screen("playing")
class Playing:
    def update(self, _dt: float) -> None:
        print("playing -> game over")
        screens.change("game_over")


@screens.screen("game_over")
class GameOver:
    def enter(self, previous: str | None) -> None:
        print("game over, previous:", previous)


screens.update(0)
screens.update(0)
