"""Distance-validated interactions and native trigger callbacks."""

from rix import Cube, Entity, Game, Interaction, Player, Text, Plane


game = Game("Interactions and Triggers")
player = Player(position=(0, 0.1, 4))
message = Text("Press E near the purple switch", x=20, y=20)
switch = Cube(z=2, y=0.5, color="#db14d1", collider=True)
switch_uses = 0


def switch_used(_actor: Entity) -> None:
    global switch_uses
    switch_uses += 1
    message.text = f"Switch used {switch_uses} time(s)!"


interaction = Interaction(
    switch,
    switch_used,
    distance=3,
)
game.input.bind("interact", "key:e")

Plane(y=0, size=20, color="#4b081e", collider=True)

@game.on_input("interact")
def use_switch() -> None:
    if not interaction.interact(player):
        message.text = "Move closer to the purple switch"


trigger = Cube(z=-3, y=1, scale=(4, 2, 0.25), color="#3f0df700", trigger=True)


@trigger.on_enter
def entered(other) -> None:  # type: ignore[no-untyped-def]
    if other == player:
        message.text = "Trigger entered!"


game.run()
