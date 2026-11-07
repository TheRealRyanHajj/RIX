"""Render and walk inside a cube with one beginner-friendly flag."""

import rix as e3


game = e3.Game("Inside a Cube")

e3.Cube(
    size=(20, 10, 20),
    color=(0.45, 0.72, 1.0, 1.0),
    double_sided=True,
    collider=False,
)
e3.Player(position=(0, 1, 0))

game.run()
