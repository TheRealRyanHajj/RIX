"""Static and dynamic objects use the production Jolt physics world."""

# Usage: from the repository root, run:
#   python examples/beginner/04_physics_playground.py

from rix import Cube, Game, Plane, Sphere, Camera

game = Game("Physics Playground", graphics_preset="ultra", fixed_hz=600)

Plane(y=0, size=30000, collider=True, friction=30, color="white")

for level in range(6):
    for column in range(6 - level):
        Cube(x=(column - (5 - level) / 2) * 1.1,y=1 + level, physics=True, mass=1, color="#4da3ff")
sphere = Sphere(position=(0,3,30), radius=1, physics=True, mass=50, color="black", velocity=(0,0,-50))
game.camera.vertical_fov_degrees = 90

@game.update
def update(dt: float) -> None:
    game.camera.look_at(sphere.position)
game.run()
