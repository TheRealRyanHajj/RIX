"""A Pygame-style loop using the same native scheduler as Game.run()."""

import rix as e3


with e3.Game("Manual Loop") as game:
    cube = e3.Cube(color="blue")

    while game.running:
        dt = game.tick(60)
        cube.ry += 90 * dt
