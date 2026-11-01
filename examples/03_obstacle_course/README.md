# Physics obstacle course

Run from the repository root after the editable install:

```powershell
python examples/03_obstacle_course/main.py
```

Controls: `WASD` or arrows to move, mouse or `Q`/`E` to turn, Space to jump,
Escape to quit. A connected gamepad can use the left stick, right-stick X, and
A. Mouse look requests pointer lock and falls back to keyboard turning when the
desktop cannot grant it.

The center lane exercises native step climbing and grounded movement. Side
lanes provide a slope and balance beams; dynamic balls exercise rigid-body
interaction. Cross the green finish gate to trigger the completion event.

For a bounded window/renderer smoke run:

```powershell
python examples/03_obstacle_course/main.py --seconds 5
```
