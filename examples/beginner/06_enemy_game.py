"""A native-character enemy automatically chases its target."""

# Usage: from the repository root, run:
#   python examples/beginner/06_enemy_game.py

import rix as e3


game = e3.Game("Enemy Game")
e3.Plane(size=100, collider=True)
player = e3.Player(y=2)
enemy = e3.Enemy(target=player, behavior="chase", position=(0, 1, -10))
game.run()
