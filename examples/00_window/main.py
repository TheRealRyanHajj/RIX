"""Phase 0 interactive native-window smoke test."""

from rix import Game


def main() -> None:
    game = Game(title="RIX — Phase 0", resolution=(1280, 720), vsync=True)
    game.run()


if __name__ == "__main__":
    main()

