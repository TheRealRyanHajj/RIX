# Using Classes

Subclass an RIX object when behavior naturally belongs to it:

```python
import rix as e3

class Spinner(e3.Cube):
    def update(self, dt):
        self.ry += 90 * dt

game = e3.Game()
spinner = Spinner(color="orange")
game.run()
```

Available lifecycle hooks include `awake`, `start`, `fixed_update`, `update`,
`late_update`, and `on_destroy`. Collision and trigger hooks are also
available. RIX discovers these methods through the normal scene scheduler;
you do not need to register each object manually.

Use ordinary composition when subclassing is unnecessary:

```python
actor = e3.Entity("Actor")
actor.add_health(100)
```
