"""RIX remains usable without importing Pygame."""

import rix

game = rix.Game(title="Standalone RIX")
rix.Cube(color="orange", scale=2, angular_velocity=(0, 45, 0), collider=False)
game.run()
