"""A complete beginner RIX obstacle course in fewer than 70 lines."""

# Usage: from the repository root, run:
#   python examples/03_obstacle_course/beginner.py

from rix import Cube, Game, Player, Sphere, Text


game = Game("My First Obstacle Course")

# The automatic camera and lights make these objects immediately visible.
Cube(y=-0.5, z=-8, scale=(16, 1, 28), color="#26382f", collider=True)

# Steps, platforms, balance beams, and walls are all ordinary cubes.
for index, height in enumerate((0.2, 0.4, 0.6)):
    Cube(
        y=height / 2,
        z=-2.5 - index,
        scale=(3, height, 1),
        color="orange",
        collider=True,
    )
Cube(y=0.3, z=-7, scale=(3, 0.6, 4), color="blue", collider=True)
Cube(x=-3.5, y=0.5, z=-5, scale=(1, 1, 8), color="purple", collider=True)
Cube(x=3.5, y=0.15, z=-5, scale=(0.8, 0.3, 8), color="yellow", collider=True)

# Dynamic objects use the same native Jolt physics system.
for x in (-2, 0, 2):
    Sphere(x=x, y=3, z=-9, radius=0.45, color="red", physics=True, mass=2)

status = Text("Reach the green gate!  WASD | Space | Shift | Ctrl", x=20, y=20)


def finish(_event: object) -> None:
    status.text = "Course complete!"


Cube(
    y=1,
    z=-14,
    scale=(5, 2, 0.3),
    color="#33dd66",
    trigger=finish,
    name="Finish gate",
)

# Player includes movement, mouse look, jumping, sprinting, crouching, and camera.
Player(position=(0, 0.1, 3), move_speed=4.5, jump_speed=5.5)
game.run()
