# RIX

RIX adds a 3D world to Python games. If you already use Pygame, you can keep
your event loop, controls, menus, sprites, and sound, then use RIX for the
3D scene, models, lighting, and physics. You can also build a game with RIX on
its own.

RIX is designed for Windows 10 and 11 (64-bit) and Python 3.11–3.13.

## Install

For a Pygame project, install RIX with its Pygame Community Edition support:

```powershell
py -m pip install "rix[pygame]"
```

For a standalone RIX game, install the core package:

```powershell
py -m pip install rix
```

The Pygame extra installs Pygame Community Edition, which you import as
`pygame` in Python.

## Add 3D to a Pygame game

Create your Pygame window as usual, then give it to `rix.World`. RIX updates
and draws the 3D scene while your game keeps control of the event loop:

```python
import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
clock = pygame.time.Clock()

world = rix.World(screen)
rix.Cube(world, color="orange", angular_velocity=(0, 45, 0), collider=False)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()

world.close()
pygame.quit()
```

In the default display mode, RIX presents the frame, so leave out
`pygame.display.flip()` and `pygame.display.update()`. If your existing game
needs to draw its own Pygame screen, use `rix.World(screen, mode="surface")`;
then blit the Surface returned by `world.render()` and present it with Pygame.
The [Pygame integration guide](docs/pygame-integration-plan.md) explains the
options, and the [migration guide](docs/guides/migrating-a-pygame-project.md)
walks through adding RIX to an existing project.

## Make a standalone 3D game

RIX can also create and manage the window, game loop, and scene for you:

```python
from rix import Cube, Game, Light, Plane, Player

game = Game("My RIX Game", (1280, 720))
Plane(y=-0.5, size=30)
Cube(position=(0, 0.5, 0), color="orange", physics=True)
Light("directional", rotation=(-45, -30, 0), intensity=1.0)
Player(position=(0, 0.1, 6), controller="first_person")
game.run()
```

The built-in first-person controls are WASD or the arrow keys to move, mouse
to look, Space to jump, Shift to sprint, and Ctrl to crouch. Escape releases
the mouse. Remap controls with `game.input.bind(...)`.

## What you can build

RIX includes 3D models and primitives, cameras, lights, skyboxes, physics,
character controllers, audio, and a 2D heads-up display. Models can be loaded
from OBJ, glTF, GLB, and FBX files, including skeletal animation. The optional
`rix.net` package provides networking for client/server games and headless
servers.

Start with the [beginner lessons](docs/guides/README.md), or browse the
[runnable examples](examples/). For specific topics, see the guides for
[FBX models](docs/fbx-importing.md),
[skeletal animation](docs/skeletal-animation.md),
[multiplayer](docs/networking.md), and
[Pygame projects](docs/guides/migrating-a-pygame-project.md).

## License

RIX is available under the [Apache License 2.0](LICENSE). Third-party
components retain their own licenses; see
[`LICENSES/THIRD_PARTY.md`](LICENSES/THIRD_PARTY.md) for details.
