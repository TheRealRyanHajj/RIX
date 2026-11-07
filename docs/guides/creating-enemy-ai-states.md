# Creating Enemy AI

Use a condition for a transition the enemy should evaluate each update:

```python
states = enemy.state_machine("patrol")

@states.state("patrol")
def patrol(dt: float) -> None:
    enemy.move((1 * dt, 0, 0))

@states.state("chase")
def chase(dt: float) -> None:
    direction = (player.position - enemy.position).normalized()
    enemy.move(direction * (3 * dt))

states.when(
    "patrol",
    "chase",
    condition=lambda: enemy.distance_to(player) < 10,
    priority=10,
)
```

Entity-owned machines advance once through the game scheduler. They freeze
while the entity is disabled and cancel when it is destroyed or detached; do
not also call `update()` manually. A detached ordinary `StateMachine` remains
manually advanceable.

Use priorities when more than one guard can be true. The transition loop is
bounded, so accidental guard cycles cannot run forever. Enter/exit callbacks
are appropriate for path resets, sounds, or one-time attack setup.
