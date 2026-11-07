"""Visible GPU lifecycle check, excluded from automated test discovery."""

from __future__ import annotations

import threading
import time

from rix import Game


def main() -> None:
    for iteration in range(2):
        game = Game(
            title=f"RIX lifecycle {iteration + 1}",
            resolution=(640, 360),
            vsync=False,
            fps_limit=120,
        )
        stopper = threading.Thread(
            target=lambda: (time.sleep(0.75), game.stop()), daemon=True
        )
        stopper.start()
        game.run()
        stopper.join()
        print(
            f"iteration={iteration + 1} frames={game.frame_count} "
            f"running={game.is_running}"
        )


if __name__ == "__main__":
    main()
