"""Third-person movement and camera follow use the same native motor."""

from rix import Cube, Game, Plane, Player, Text


game = Game("Third Person")
Plane(y=-0.5, size=40, collider=True)
player = Player(position=(0, 0.1, 3), controller="third_person")
Cube(parent=player, y=0.9, scale=(0.8, 1.8, 0.8), color="blue", collider=False)
Text("Move with WASD or a gamepad", x=20, y=20)
game.run()
