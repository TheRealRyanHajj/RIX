"""A Pygame-style loop using the same native scheduler as Game.run()."""

# Usage: from the repository root, run:
#   python examples/beginner/03_manual_loop.py

import rix as e3


with e3.Game("Manual Loop") as game:
    cube = e3.Cube(color="blue")

    while game.running:
        dt = game.tick(60)
        cube.ry += 90 * dt
