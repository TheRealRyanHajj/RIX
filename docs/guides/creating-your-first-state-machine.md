# Creating Your First State Machine

State machines work without Pygame, rendering, physics, or networking:

```python
from rix import StateMachine

states = StateMachine("idle")

@states.state("idle")
def idle(dt: float) -> None:
    print("waiting", dt)

@states.state("run")
def run(dt: float) -> None:
    print("moving", dt)

states.change("run")
states.update(1 / 60)
```

Read `current`, `previous`, and `elapsed`. Use `pause()`, `resume()`, and
`reset()` for lifecycle control. Enter/exit decorators run exactly once for a
committed transition, and `after(seconds, target)` returns a cancelable timer.

The advanced `add_state`, `add_transition`, `start`, and `trigger` API uses the
same transition engine. `examples/states/01_basic.py` is the smallest runnable
version.
