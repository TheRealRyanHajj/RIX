"""Multiple colored lights in a few lines."""

from rix import Cube, Game, Light, Plane

game = Game(graphics_preset="high")
Plane(size=(18, 18), y=-0.05, color="gray")
Cube(position=(-2, 1, 0), color="white")
Cube(position=(2, 1, 0), color="white")
Light("point", position=(-3, 3, 1), color="red", intensity=12, range=10)
Light("point", position=(3, 3, 1), color="blue", intensity=12, range=10)
Light("spot", position=(0, 6, 4), rotation=(-55, 180, 0), color="white",
      intensity=18, range=16, angle=50, casts_shadows=True)
game.run()
