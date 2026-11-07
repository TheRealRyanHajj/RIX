# Your First 3D Game

Install the editable project, create `game.py`, and write:

```python
from rix import Cube, Game

game = Game()
Cube()
game.run()
```

`Game` already owns a scene, camera, native renderer, input, ambient light and
directional light. Close the native window to return from `run()` and release
resources. Run the repository version with:

```powershell
.venv\Scripts\python.exe examples\beginner\01_first_scene.py
```

Use `with Game() as game:` when you want automatic cleanup after an exception.
Explicit scenes remain available for applications that need ownership control.
