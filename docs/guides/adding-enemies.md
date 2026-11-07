# Adding Enemies

```python
from rix import Enemy, Game, Plane, Player

game = Game()
Plane(y=-0.5, size=40, collider=True)
player = Player(position=(0, 0.1, 5))
enemy = Enemy(position=(0, 0.1, -5), target=player,
              behavior="chase", health=100, speed=3)
enemy.health.on_death(lambda event: enemy.destroy())
game.run()
```

`Enemy` is an optional preset, not a mandatory base class. Build custom actors
from `Health`, `HitscanWeapon`, `Interaction`, `SpawnPoint`, `Respawner`,
`Scoreboard`, `TeamRoster`, timers and `StateMachine`. Hitscan uses the first
native collision, so walls and cover block damage.
