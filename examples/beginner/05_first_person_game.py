"""One constructor provides first-person movement, view, sprint, and crouch."""

import rix as e3


game = e3.Game("First-Person Game")
e3.Plane(size=100, collider=True)
player = e3.Player(y=2)
game.run()
