"""One constructor provides first-person movement, view, sprint, and crouch."""

# Usage: from the repository root, run:
#   python examples/beginner/05_first_person_game.py

import rix as e3


game = e3.Game("First-Person Game")
e3.Plane(size=100, collider=True)
player = e3.Player(y=2)
game.run()
