# Add RIX to an existing Pygame project

RIX is designed to leave the application model in Pygame. Keep the Pygame
window, clock, event loop, sprites, fonts, controls, mixer, and 2D UI. Add one
`rix.World`, forward each event after your own handlers see it, advance the
world with the same `dt`, and choose one presentation mode.

## Before: ordinary Pygame

```python
import pygame

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 32)
player = pygame.sprite.Sprite()
player.image = pygame.Surface((40, 40), pygame.SRCALPHA)
player.image.fill("orange")
player.rect = player.image.get_rect(center=(480, 270))
sprites = pygame.sprite.Group(player)
sound = pygame.mixer.Sound("assets/click.wav")

running = True
while running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            sound.play()

    keys = pygame.key.get_pressed()
    player.rect.x += (keys[pygame.K_d] - keys[pygame.K_a]) * 240 * dt
    screen.fill("midnightblue")
    sprites.draw(screen)
    screen.blit(font.render("Pygame game", True, "white"), (20, 20))
    pygame.display.flip()

pygame.quit()
```

## After: compatibility Surface mode

This mode requires the fewest rendering changes. Pygame remains the only
presenter, so direct drawing to `screen` and `pygame.display.flip()` keep their
normal meaning.

```python
import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.Font(None, 32)
# Existing sprite, group, and mixer setup stays unchanged.

world = rix.World(screen, mode="surface")
rix.Cube(world, position=(0, 0, 0), color="orange")
rix.Plane(world, y=-1, size=30, collider=True, color="gray")

running = True
while running and world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        # Existing event handlers, including sound.play(), stay here.
        world.handle_event(event)  # forwards this object; never drains the queue

    # Existing pygame.key.get_pressed(), sprite updates, and game logic stay.
    world.update(dt)
    frame_3d = world.render()  # blocking compatibility readback; no presentation
    screen.blit(frame_3d, (0, 0))
    sprites.draw(screen)
    screen.blit(font.render("Pygame + RIX", True, "white"), (20, 20))
    pygame.display.flip()

world.close()  # release bgfx while Pygame's HWND still exists
pygame.quit()
```

For a small inventory/map/character preview, use
`rix.Viewport(world, rect=..., camera=...)` instead of reading the full window.
Its camera and render size are independent; after its first image, default
refreshes are buffered and return cached output until the GPU copy completes.

## After: direct GPU mode

Use `World(screen)` for the fastest full-window 3D path. In this mode bgfx is
the sole presenter. Do not call `pygame.display.flip()` or draw UI directly to
the display Surface. Draw the unchanged Pygame UI to a transparent intermediate
Surface, install it once with `world.set_overlay(ui)`, and call
`world.overlay.update(ui)` after modifying its pixels.

```python
world = rix.World(screen)  # mode="gpu"
ui = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
world.set_overlay(ui)

# Inside the existing loop, after world.update(dt):
ui.fill((0, 0, 0, 0))
sprites.draw(ui)
ui.blit(font.render("Pygame + RIX", True, "white"), (20, 20))
world.overlay.update(ui)
world.render()  # RIX performs the one final presentation
```

Pygame mixer remains the default audio system in both modes. RIX does not open
its native spatial-audio device in a Pygame-owned `World`; opt into standalone
native audio only when positional 3D playback is specifically needed.
