# State machines

`StateMachine` is a graphics-independent Python utility. It works in ordinary
Python, Pygame, RIX entities, and headless servers.

## First state machine

```python
from rix import StateMachine

states = StateMachine("idle")

@states.state("idle")
def idle(dt: float) -> None:
    print("waiting")

@states.state("run")
def run(dt: float) -> None:
    print("running")

states.update(1 / 60)  # starts and updates idle
states.change("run")
```

The declared initial state starts on the first `update()`, after decorators are
installed. `current`, `previous`, `elapsed`/`time_in_state`, `states`, and
`paused` expose state. `pause()`, `resume()`, `reset()`, and `stop()` control
lifetime.

## Lifecycle and transitions

```python
@states.enter("run")
def entered(previous: str | None) -> None:
    pass

@states.exit("run")
def exited(next_state: str | None) -> None:
    pass

states.when("idle", "run", condition=can_run, priority=10)
timer = states.after(3.0, "idle", state="run")
timer.cancel()
```

Event transitions remain available through `add_transition()` and `trigger()`.
Conditions run after the state's update and timers, in descending priority with
stable registration order. A configured transition limit prevents condition
loops. A `change()` requested inside a callback commits after that callback;
reentrant direct mutation is rejected. Enter failure restores the source state
and its animation selection. State-local timers stop advancing while paused and
are cancelled when their source state exits.

## Entity ownership

```python
class Guard(rix.Entity):
    def start(self) -> None:
        states = self.state_machine("patrol")

        @states.state("patrol", animation="walk")
        def patrol(dt: float) -> None:
            pass
```

An entity-owned machine is registered exactly once with its `Game`. It freezes
while the entity or scene is disabled, and its managed callback is cancelled on
entity destruction or scene detachment. A detached standalone machine remains
manually updateable.

`animation=` selects a name through the entity's `AnimationSelection`. Selecting
the same name does not restart unless `play(name, restart=True)` is used. This
is clip-selection intent; the current renderer does not claim GPU-skinned glTF
playback.

Use `GameStates` for Pygame menu/overlay stacks. Use `ServerMatchState` for the
explicit server-authoritative replicated match phase. Neither local state
machine is networked automatically.
