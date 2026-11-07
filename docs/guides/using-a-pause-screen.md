# Using a Pause Screen

Push an overlay instead of replacing gameplay:

```python
@states.screen("paused")
class Paused:
    def event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            states.pop()

    def draw(self, screen: pygame.Surface) -> None:
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        screen.blit(shade, (0, 0))

states.push("paused")
```

By default the underlying gameplay remains visible, stops updating, and does
not receive input. Drawing stays bottom-to-top and the overlay receives events.

Advanced screens can opt into propagation when registered:

```python
@states.screen(
    "inventory",
    update_underlay=True,
    event_underlay=False,
    draw_underlay=True,
)
class Inventory:
    pass
```

Screen-local timers advance only when their screen participates in the update
pass. `close()` cancels timers, exits owned instances, and is idempotent.
