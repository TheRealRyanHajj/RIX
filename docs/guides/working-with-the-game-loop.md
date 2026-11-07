# Working With the Game Loop

Managed mode is the default. RIX polls events, advances fixed physics,
runs callbacks, renders, and presents for you:

```python
import rix as e3

game = e3.Game()
cube = e3.Cube()

@game.update
def update(dt):
    cube.ry += 90 * dt

game.run()
```

Manual mode has a Pygame-style outer loop but uses the same scheduler:

```python
with e3.Game() as game:
    cube = e3.Cube()
    while game.running:
        dt = game.tick(60)
        cube.ry += 90 * dt
```

Each `tick()` performs event polling, input finalization, fixed simulation and
callbacks, rendering, presentation, and optional frame limiting, then returns
elapsed seconds. Code after `tick()` is visible on the next presented frame.
The context manager guarantees cleanup if the loop exits or raises.

Do not mix `run()` and `tick()` on the same active loop. Recursive ticks and
cross-thread manual stepping raise clear exceptions. Python callbacks always
run on the gameplay/window thread.
