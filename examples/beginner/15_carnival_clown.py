"""Launch physical projectiles along the player's live view direction."""

# Usage: from the repository root, run:
#   python examples/beginner/15_carnival_clown.py

from rix import Cube, Game, Plane, Player, Sphere, Vec3


game = Game("Clown Game")
game.camera.vertical_fov_degrees = 80
Plane(size=500, collider=True, color="#405065", friction=130)
for level in range(12):
    for column in range(12 - level):
        Cube(x=(column - (11 - level) / 2) * 1.1,y=1 + level, z=5, physics=True, mass=4, color="#4da3ff")

player = Player(y=1, controls=True)


@game.on_mouse("left")
def fire() -> None:
    direction = player.view_forward
    projectile = Sphere(
        position=player.world_position + Vec3(0, 1.35, 0) + direction,
        radius=.1,
        physics=True,
        gravity=True,
        continuous=True,
        color="#ffd45a",
        mass=12
    )
    projectile.launch(direction, 250, face=True)

game.run()
