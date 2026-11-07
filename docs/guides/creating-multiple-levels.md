# Creating Multiple Levels

The automatic scene is enough for one level. Create explicit scenes when your
game needs more:

```python
import rix as e3

game = e3.Game()
level_two = e3.Scene("Level Two")

with level_two:
    e3.Plane(size=50, collider=True)
    e3.Cube(color="blue")

game.load_scene(level_two)
game.run()
```

A scene can belong to only one game at a time. Loading a replacement detaches
the previous scene without silently copying its entities. Scene changes occur
between runs/frames, not while a native frame is being rendered.
