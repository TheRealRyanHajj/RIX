# Reading Input

Read held physical controls directly:

```python
if game.input.key("space"):
    print("Space is held")

if game.input.mouse("left"):
    print("Left mouse is held")
```

`pressed` and `released` are true only on the transition frame. If the name is
a bound action it reads that action; otherwise it reads a physical keyboard
key:

```python
if game.input.pressed("e"):
    interact()
```

Decorators are convenient for one-shot actions:

```python
@game.on_key("space")
def jump():
    pass

@game.on_mouse("left")
def shoot():
    pass
```

For remapping and gamepads, bind a named action and use `value`, `down`,
`pressed`, and `released`:

```python
game.input.bind("interact", "key:e", "gamepad:x")
```
