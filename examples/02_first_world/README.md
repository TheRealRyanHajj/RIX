# First world

This Phase 1 example creates a native scene with a perspective camera, ambient
and directional lighting, transformed primitives, a decoded PNG texture, a
textured OBJ/MTL model, depth testing, and debug axes. It uses only RIX's
public Python API, moves the camera from an entity `update` callback, and
destroys every scene entity after the window closes.

From an activated editable-install environment:

```powershell
python examples/02_first_world/main.py
```

For repeatable automated lifecycle checks, pass a positive duration:

```powershell
python examples/02_first_world/main.py --seconds 5
```
