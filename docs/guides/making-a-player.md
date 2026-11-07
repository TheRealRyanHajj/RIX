# Making a Player

```python
from rix import Game, Plane, Player

game = Game("Player")
Plane(y=-0.5, size=40, collider=True)
player = Player(position=(0, 0.1, 4), controller="first_person")
game.run()
```

WASD and arrows move, mouse/gamepad aim, Space jumps, Shift sprints, Ctrl
crouches, Escape releases the mouse, and left click captures it. The persistent
camera follows automatically. Use `controller="third_person"` for the chase
camera preset.

Sensitivity, speed, ground/air acceleration, friction, air projection cap, jump
speed, slope, step height, sprint multiplier and crouch dimensions are
constructor options. Pass `controls=False` when your own code will call
`move()`.

Jump is edge-triggered: holding Space does not automatically jump again. To
bunny hop, press jump on the first grounded landing tick. That tick skips ground
friction and carries horizontal momentum into takeoff. Air movement accelerates
only along the requested direction, so forward-only input cannot add speed once
that projection is full, while a well-timed strafe turn can.
Remap any default action through `game.input.bind(...)`.
