"""A managed update callback rotates one persistent native object."""

# Usage: from the repository root, run:
#   python examples/beginner/02_spinning_cube.py

import rix as e3, math

game = e3.Game("Spinning Cube")
cube = e3.Cube(texture="grass.png")

@game.update
def update(dt: float) -> None:
    cube.ry += 90 * dt

game.run()
