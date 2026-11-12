"""Migration: replace easy3d imports; standalone behavior is otherwise the same."""

# Usage: from the repository root, run:
#   python examples/pygame/13_migration.py

# Old, temporarily supported with a DeprecationWarning:
# from easy3d import Cube, Game

from rix import Cube, Game

game = Game(title="Migrated RIX project")
Cube(color="orange", scale=2, angular_velocity=(0, 45, 0), collider=False)
game.run()
