# Using State Machines

Standalone state machines remain manually updateable. The shortest form uses
an initial state and decorators:

```python
from rix import StateMachine

states = StateMachine("idle")

@states.state("idle")
def idle(dt: float) -> None:
    if should_move():
        states.change("moving")

@states.state("moving")
def moving(dt: float) -> None:
    move_actor(dt)

states.update(dt)
```

To attach one to an entity and let the game advance it exactly once per render
update:

```python
machine = rix.StateMachine()
machine.add_state("idle")
machine.add_state("moving")
machine.start("idle")
actor.add_state_machine(machine)
```

Timers can likewise remain standalone or be registered:

```python
timer = rix.Timer(2, callback=lambda: spawn_enemy())
game.manage_timer(timer)
```

For ordinary delays, `game.after(seconds, callback)` and
`game.every(seconds, callback)` are shorter and return cancellable handles.

```python
from rix import Game, StateMachine

game = Game()
states = StateMachine()
states.add_state("idle")
states.add_state("running", on_update=lambda dt: print(dt))
states.add_transition("idle", "running", "move")
states.add_transition("running", "idle", "stop")
states.start("idle")

@game.update
def update(dt):
    states.update(dt)

@game.on_key("space")
def toggle():
    states.trigger("move" if states.current == "idle" else "stop")

game.run()
```

Changes requested from a state callback are committed when that callback
returns. Guards are ordinary callables, conditions use stable priority order,
and the transition count per update is bounded. Use fixed-update callbacks when
the state controls deterministic simulation rather than visual presentation.

For Pygame menus, pause overlays, and screen stacks, use `GameStates`; see
`docs/game-states.md`.
