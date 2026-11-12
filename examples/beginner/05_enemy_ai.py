"""Composable health and a native-motor chase enemy."""

# Usage: from the repository root, run:
#   python examples/beginner/05_enemy_ai.py

from rix import Enemy, Game, Plane, Player, Text


game = Game("Simple Enemy AI")
Plane(y=-0.5, size=40, collider=True)
player = Player(position=(0, 0.1, 5))
enemy = Enemy(position=(0, 0.1, -6), target=player, health=100, speed=2.5)
label = Text("Enemy health: 100", x=20, y=20)
enemy.health.on_change(lambda health: setattr(label, "text", f"Enemy health: {health.current:.0f}"))
game.run()
