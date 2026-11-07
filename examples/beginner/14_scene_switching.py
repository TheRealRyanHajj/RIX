"""Load two explicit scenes across successive native window runs."""

from rix import Camera, Cube, Game, Light, Scene, Text


game = Game("Scene One")
first = game.scene
with first:
    Cube(color="orange")
    Text("Close the window to load scene two", x=20, y=20)
second = Scene("Second")
second.camera = Camera(position=(4.5, 3, 6.5)).look_at((0, 0, 0))
with second:
    Light("ambient", intensity=0.3)
    Light("directional", rotation=(-45, -35, 0))
    Cube(color="blue", scale=2)
    Text("Scene two", x=20, y=20)

game.load_scene(first)
game.run()
game.load_scene(second)
game.run()
