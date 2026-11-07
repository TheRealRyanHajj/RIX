"""Launch physical projectiles along the player's live view direction."""

from rix import Cube, Game, Plane, Player, Sphere, Vec3


game = Game("Projectile Motion")
Plane(y=-0.5, size=50, collider=True, color="#405065")
for x in (-4, -2, 0, 2, 4):
    Cube(x=x, y=0.5, z=-12, collider=True, color="#e48b55")

player = Player(y=1, controls=True)

# This entity has no Rigidbody. Native fixed-step integration still moves and
# rotates it using world units/second and degrees/second.
marker = Cube(
    x=-4,
    y=4,
    z=-8,
    scale=0.35,
    color="#61d4ff",
    collider=False,
    velocity=(1.5, 0, 0),
    angular_velocity=(20, 60, 0),
)


@game.on_mouse("left")
def fire() -> None:
    direction = player.view_forward
    projectile = Sphere(
        position=player.world_position + Vec3(0, 1.35, 0) + direction,
        radius=0.18,
        physics=True,
        gravity=True,
        continuous=True,
        color="#ffd45a",
    )
    projectile.launch(direction, 40, face=True)

game.run()
