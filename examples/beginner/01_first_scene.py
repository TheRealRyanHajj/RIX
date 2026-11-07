"""Your first visible 3D scene."""

from rix import Cube, Game, Plane


game = Game("My First 3D Scene")
Plane(y=0, size=20, collider=True)
Cube(y=1, color="orange")
game.run()
