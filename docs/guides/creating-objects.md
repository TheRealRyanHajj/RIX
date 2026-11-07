# Creating Objects

```python
from rix import Cube, Game, Sphere

game = Game()
parent = Cube(x=2, y=1, ry=45, scale=(2, 1, 2), color="#ff7733")
Sphere(parent=parent, position=(0, 1.5, 0), radius=0.4, color="blue")
parent.move((0, 0, -2)).rotate((0, 20, 0))
game.run()
```

Children use native transform propagation. Use either `position=(x,y,z)` or
coordinate aliases, not both. The same rule applies to `rotation` and aliases.
Colors accept documented names, `#RRGGBB`/`#RRGGBBAA`, RGB or RGBA.

Useful helpers include `look_at`, `distance_to`, `show/hide`, `enable/disable`,
`teleport`, `destroy`, and `destroy_after` for Game-owned entities.
