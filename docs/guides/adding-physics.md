# Adding Physics

```python
from rix import Game, Plane, Sphere

game = Game()
Plane(y=-0.5, size=30, friction=0.8)
Sphere(y=6, physics=True, mass=3, bounciness=0.5, continuous=True)
game.run()
```

World geometry creates a static collider by default; use `collider=False` for
visual-only geometry. `physics=True` creates the matching dynamic collider and
native Jolt rigid body. Options cover gravity, friction,
restitution (`bounciness`), collision layer, continuous detection and kinematic
bodies. Unsupported combinations raise before a partial entity survives.

Advanced code can add `Collider`, `PhysicsMaterial`, `Rigidbody`, constraints,
queries and collision callbacks explicitly. Physics-owned transforms must use
`teleport` rather than ordinary per-frame position writes.
