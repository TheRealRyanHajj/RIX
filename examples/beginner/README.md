# Beginner examples

Run these scripts from the repository root with the active RIX environment:

```powershell
.venv\Scripts\python.exe examples\beginner\01_first_scene.py
```

Start with `01_first_scene.py`, `02_spinning_cube.py`, and
`03_manual_loop.py`. The remaining scripts cover first- and third-person
controllers, physics, enemy AI, raycast interactions, state machines,
triggers, retained HUD layout, audio, and explicit scene switching. They
contain game code only—smoke-test deadlines, benchmark assertions, and
repeated teardown live in `tests/` and `benchmarks/`.

`10_inside_a_cube.py` is the focused face-culling lesson. It uses
`double_sided=True` to render a room from inside one cube; press Escape to
release the mouse and close the window normally.

`11_multiple_lights.py` introduces point and spot lights with local shadows.
`12_skyboxes.py` shows procedural, panoramic, cubemap, disabled, and restored
scene skies. The combined stress/visual example is `examples/15_lighting_sky`.

`13_projectile_motion.py` demonstrates universal entity velocity and angular
velocity, plus left-click physical projectiles launched along
`Player.view_forward` with continuous collision detection.
