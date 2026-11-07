# GameStates

`GameStates` is a small Pygame-friendly screen and overlay manager. It has no
renderer, physics, or networking dependency.

## Smallest screen loop

```python
import pygame
from rix import GameStates

screens = GameStates("menu")

@screens.screen("menu")
class Menu:
    def event(self, event: object) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            screens.change("playing")

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("navy")

@screens.screen("playing")
class Playing:
    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")

for event in pygame.event.get():
    screens.event(event)
screens.update(dt)
screens.draw(screen)
```

`enter(previous)`, `exit(next_state)`, `event(event)`, `update(dt)`,
`fixed_update(dt)`, and `draw(surface)` are all optional. Each registered class
is instantiated once and remains owned by that manager until `close()`.

## Pause overlays and propagation

`push(name)` places an overlay above the current screen and `pop()` removes it.
The default policy draws the underlay, but suspends its updates and prevents it
from receiving input:

```python
@screens.screen("pause")
class Pause:
    def draw(self, surface: pygame.Surface) -> None:
        surface.fill((0, 0, 0, 120))

screens.push("pause")
```

Configure a screen when it should expose part of the stack below it:

```python
@screens.screen(
    "hud",
    update_underlay=True,
    event_underlay=False,
    draw_underlay=True,
)
class Hud:
    pass
```

- Events travel from the top screen downward while `event_underlay=True`.
- Variable and fixed updates run from the lowest included screen upward while
  `update_underlay=True`.
- Drawing runs from bottom to top. `draw_underlay=False` starts drawing at that
  screen and hides everything below it.
- A screen-local `after()` timer advances only while its owner is included in
  the update pass. Leaving the owner cancels the timer.

Use `policy(name)` to inspect the immutable `ScreenPolicy`, `get(name)` to
retrieve the single owned instance, `registered` to inspect registered names,
and `stack` to inspect active bottom-to-top names. Reusing the same class or
object under two names, pushing a duplicate name, or popping the final screen
raises an error instead of creating ambiguous ownership.

State changes requested from event, update, fixed-update, or draw callbacks are
deferred until that dispatch finishes. `close()` exits active screens from top
to bottom, cancels their timers, releases cached instances, and may be called
more than once.
