# Making a Menu

```python
from rix import Button, Game, Row, Text

game = Game("Menu")
status = Text("Ready", x=20, y=20)
with Row(anchor="bottom", gap=10, padding=16):
    Button("Play", click=lambda: setattr(status, "text", "Playing"))
    Button("Quit", click=game.stop)
game.run()
```

Direct elements use the active scene HUD. Row, Column, Stack and Grid calculate
retained native element positions and may nest. ProgressBar, HealthBar, Image,
Sprite and ScoreboardPanel use the same renderer and hit-testing path. HUD units
are framebuffer pixels; see known issues for current font, DPI, clipping and
keyboard-focus limits.
