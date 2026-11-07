# Physics obstacle course

Run from the repository root after the editable install:

```powershell
python examples/03_obstacle_course/beginner.py
```

`beginner.py` is the recommended under-70-line version and uses automatic game
setup, the complete default Player controller, physics shortcuts, named colors,
direct HUD construction, and a trigger callback. `main.py` remains the advanced
diagnostic version with CLI deadlines and renderer assertions used by tests.

Controls: `WASD` or arrows to move, mouse or Left/Right arrows to turn, Space to
jump, Shift to sprint, Ctrl to crouch, and Escape to quit. A connected gamepad
can use the left stick, right-stick X, and button A. Mouse look requests pointer
lock and falls back to arrow-key turning when the desktop cannot grant it.
`Tab`, `Q`, and `E` are bound as reserved actions but intentionally have no
behavior in this sample.

The center lane exercises native step climbing and grounded movement. Side
lanes provide a slope and balance beams; dynamic balls exercise rigid-body
interaction. Cross the green finish gate to trigger the completion event.

For a bounded window/renderer smoke run:

```powershell
python examples/03_obstacle_course/main.py --seconds 5
```
