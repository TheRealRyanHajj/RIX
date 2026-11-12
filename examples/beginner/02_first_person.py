"""Python module for the RIX example in examples/beginner.

Run from the repository root with `python examples/beginner/02_first_person.py`. Check
the nearby README for controls, assets, or multi-process startup instructions."""

from rix import Cube, Game, Light, Plane, Player

game = Game("My first Game!")
Plane(y=0, size=40, texture="grass.png")

for x, z in ((-4, -5), (0, -8), (4, -5)):
    Cube(x=x, y=1, z=z, scale=(2, 2, 2), texture="image.png")

Player(position=(0, 0, 4), controller="first_person")
game.run()