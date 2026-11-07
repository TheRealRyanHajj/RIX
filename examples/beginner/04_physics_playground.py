"""Static and dynamic objects use the production Jolt physics world."""

from rix import Cube, Game, Plane, Sphere


game = Game("Physics Playground")
Plane(y=-0.5, size=30, collider=True)
for level in range(6):
    for column in range(6 - level):
        Cube(
            x=(column - (5 - level) / 2) * 1.1,
            y=0.5 + level,
            physics=True,
            mass=2,
            color="#4da3ff",
        )
Sphere(x=0, y=8, radius=1, physics=True, mass=8, bounciness=0.4, color="orange")
game.run()
