"""Look at the orange cube and press E to destroy it."""

import rix as e3


game = e3.Game("Simple Interaction")
e3.Plane(size=100, collider=True)
player = e3.Player(y=0)
target = e3.Cube(
    position=(0, 1, -4),
    scale=2,
    collider=True,
    color="orange",
)
message = e3.Text("Look at the orange cube and press E", x=20, y=20)


@game.on_key("e")
def interact() -> None:
    hit = player.raycast(5)
    if hit is None or hit.entity != target:
        message.text = "Nothing in reach"
        return
    target.destroy()
    message.text = "Cube destroyed!"


game.run()
