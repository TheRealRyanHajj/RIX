# Making a Menu

`GameStates` forwards only the methods each Pygame screen actually implements:

```python
import pygame
from rix import GameStates

states = GameStates("menu")

@states.screen("menu")
class Menu:
    def event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            states.change("playing")

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill("navy")

@states.screen("playing")
class Playing:
    def draw(self, screen: pygame.Surface) -> None:
        screen.fill("black")
```

The ordinary loop stays small:

```python
for event in pygame.event.get():
    states.event(event)
states.update(dt)
states.draw(screen)
```

Changes requested inside callbacks are deferred safely. Optional `enter`,
`exit`, `update`, and `fixed_update` methods need no base class. A screen may
hold a RIX `World`, but menus do not need a 3D scene.
