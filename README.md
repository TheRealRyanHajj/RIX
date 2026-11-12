# RIX — High-performance 3D for Pygame and Python

RIX is a Windows-first 3D engine for Python and Pygame Community Edition.
Pygame remains the application layer—window, event loop, timing, Surfaces,
sprites, fonts, menus, and ordinary audio—while RIX supplies native C++20
D3D11 rendering, Jolt physics, 3D scenes, lights, models, and controllers
through a typed Python API. Standalone RIX remains supported.

RIX includes optional native multiplayer for Pygame-only, RIX 3D, standalone,
and headless programs. `rix.net` provides safe named messages, direct-IP and
LAN connections, dedicated/listen servers, registered replication and RPCs.
No hosted matchmaking, arbitrary NAT traversal, or managed relay service is
claimed.

## Requirements

- Windows 10 or 11, x64
- Python 3.11, 3.12, or 3.13
- Pygame Community Edition 2.5.8 for the Pygame integration extra
- Visual Studio 2022 Build Tools or newer with Desktop development with C++
- CMake 3.26+ and Ninja (pip can provide Ninja for editable builds)
- Git and internet access for the first CMake dependency fetch

The supported compiler is MSVC. Run native build commands from an x64 Native
Tools command prompt, or import the Visual Studio developer environment into
PowerShell.

## Install

Install RIX with its optional Pygame integration using:

```powershell
py -3.11 -m pip install "rix[pygame]"
```

For a standalone RIX game without Pygame, install `rix` without the extra. RIX
currently targets 64-bit Windows and Python 3.11–3.13. A compatible prebuilt
wheel is required for normal installation; building from source also requires
the native toolchain listed above.

## Developer setup

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[pygame,dev]'
python -c "import rix; print(rix.engine_version())"
python -m pytest -q
```

If CMake selects MinGW from a regular terminal, open an x64 Visual Studio
developer shell and repeat the editable install.

The verified multiplayer/state-system release evidence is recorded in
[the Phase 16 completion report](docs/phase16-report.md).

FBX and skeletal animation are native and require no Autodesk SDK. See the
[FBX guide](docs/fbx-importing.md), [animation guide](docs/skeletal-animation.md),
and [retargeting limits](docs/animation-retargeting.md).

For the standalone native targets:

```powershell
cmake --preset windows-debug
cmake --build --preset windows-debug
ctest --preset windows-debug
```

## Migrating from Easy3D

The distribution and native extension were renamed without resetting version
history: use `import rix` and `rix._rix`. The temporary `easy3d` facade emits a
`DeprecationWarning` and forwards to the exact same Python classes and native
module; it is not a second engine. Replace imports such as
`from easy3d import Cube` with `from rix import Cube`.

## First game

### Add 3D to Pygame

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

world.close()  # release bgfx before pygame destroys the HWND
pygame.quit()
```

Direct GPU mode makes RIX the only presenter: do not call
`pygame.display.flip()` or `update()`. For existing software-display projects,
use `World(screen, mode="surface")`; `world.render()` then returns a Surface for
Pygame to blit and flip. See [the ownership and integration guide](docs/pygame-integration-plan.md).
For a before/after conversion that keeps an existing event loop, sprites,
fonts, controls, mixer, and UI, see [the Pygame migration guide](docs/guides/migrating-a-pygame-project.md).

Install without the optional Pygame dependency using `.[dev]` when only the
standalone API is needed.

### Standalone RIX

```python
from rix import Cube, Game, Light, Plane, Player

game = Game("My RIX Game", (1280, 720), vsync=True)
Plane(y=-0.5, size=30, collider=True)
Cube(position=(0, 0.5, 0), color="orange", physics=True)
Light("directional", rotation=(-45, -30, 0), intensity=1.0)
Player(position=(0, 0.1, 6), controller="first_person")
game.run()
```

Or use a manual standalone loop over the same native scheduler:

```python
import rix

with rix.Game() as game:
    cube = rix.Cube(color="blue", collider=False)
    while game.running:
        dt = game.tick(60)
        cube.ry += 90 * dt
```

Default player controls are WASD or arrows to move, mouse to look, Space to
jump, Shift to sprint, Ctrl to crouch, and Escape to release pointer capture.
All actions are remappable through `game.input.bind(...)`.

Built-in world geometry is collidable by default. Use `collider=False` for a
decorative, parented, or universal-motion visual; use `physics=True` for a
dynamic body or a kinematic rigid body for a scripted moving obstacle.

Run the maintained examples from the repository root:

```powershell
python examples\00_window\main.py
python examples\03_obstacle_course\main.py
python examples\09_hud\main.py
python examples\10_audio\main.py
python examples\11_gltf\main.py
python examples\12_diagnostics\main.py
python examples\13_autotexture\main.py
python examples\14_face_culling\main.py --view outside
python examples\beginner\01_first_scene.py
python examples\beginner\02_spinning_cube.py
python examples\beginner\03_manual_loop.py
python examples\beginner\10_inside_a_cube.py
python examples\beginner\13_projectile_motion.py
python examples\pygame\01_cube.py
python examples\pygame\04_overlay.py
python examples\pygame\07_inventory_viewport.py
python examples\pygame\14_hybrid_minigame.py
```

## Main API

- `World`: Pygame-owned window/event/timing adapter with direct GPU and Surface
  compatibility modes, fixed-step update, event forwarding, overlays, and
  deterministic close order. `attach_session()` optionally pumps one or more
  `rix.net.Session` objects from the same `world.update(dt)` call.
- `SurfaceTexture`, `Viewport`, and `Billboard`: explicit Pygame Surface GPU
  upload/update, camera-independent buffered Rect-sized previews, and
  camera-facing world sprites. Full-window Surface mode and an explicitly
  blocking Viewport refresh remain synchronous compatibility operations.

- `Game`: native window, update/fixed-update callbacks, timers, input, renderer
  settings, scene ownership, blocking `run()`, manual `tick()`, and clean
  shutdown.
- `Scene` and `Entity`: generational native handles, transform hierarchy,
  components, fixed-step linear/angular motion, facing/launch helpers, lookup,
  explicit destruction, and context-local construction.
- `Cube`, `Sphere`, `Plane`, and `Model`: convenient renderable entities;
  `Model` loads OBJ/glTF/GLB/FBX and owns typed skeletal playback controls.
- `Player` and `CharacterController`: first-/third-person movement, jumping,
  sprinting, crouching, slopes, steps, and camera follow.
- `Collider`, `Rigidbody`, `Constraint`, and physics queries: Jolt-backed rigid
  bodies, triggers, collision callbacks, raycasts, sweeps, overlaps, CCD, and
  joints.
- `Camera`, `Light`, `Lighting`, and `Skybox`: projections, camera control,
  bounded directional/point/spot lights, per-light shadows, procedural/image
  skies, post-processing presets, and debug drawing.
- `HUD`, layout containers, text, sprites, bars, and buttons: retained native
  2D overlays with pointer interaction.
- `Audio`, `Sound`, and `AudioSource`: WAV playback, mixing, and positional
  audio.
- `load_obj`, `load_gltf`, `TextureCache`, and `ModelCache`: pinned native asset
  import and caching.
- AutoTexture: filename-only missing PNG generation, 16 px/unit world-scale
  tiling, cube atlases, spherical/authored UVs, tangent-space normal maps,
  roughness/metallic/emissive/AO maps, mipmaps, and development hot reload.
- gameplay helpers: health, enemies, hitscan weapons, teams, scoring,
  interactions, respawn, state machines, events, timers, cooldowns, and tweens.
- beginner shortcuts: scalar movement/rotation, scene-free raycasts, raw
  key/mouse helpers, one-call cached audio, attached health/weapons, and managed
  timers/state machines/tweens.

The ordered beginner learning path is in `docs/guides/README.md`. Advanced
facades remain available at the root and are curated in `rix.advanced`;
timing utilities are also available from `rix.time`.

The public API is typed. Native implementation details remain private behind
`rix._rix` and are not compatibility promises.

## Optional multiplayer and state systems

`rix.net` provides safe named messages, independent headless servers and
clients, listen hosting, LAN discovery, direct-IP connections, registered
prefab/state replication, bounded RPCs, interest management, and supported
character prediction/reconciliation. It does not initialize Pygame, a window,
or a renderer unless the application does so separately. Hosted matchmaking,
arbitrary NAT traversal, a managed relay service, and generic rollback are not
claimed.

The complete public sample set is indexed in
`examples/networking/README.md`: twelve examples use real native connections
and the thirteenth is clearly labeled as a finite seeded impairment simulator.
State and screen-management examples are indexed under `examples/states`.

```python
from rix import net

session = net.Session()
session.join("127.0.0.1:7777")

@session.on("chat")
def chat(sender: net.Player, *, text: str) -> None:
    print(sender.id, text)
```

## Textures in one line

```python
import rix as e3

game = e3.Game()
e3.Plane(size=30, texture="assets/grass.png")
e3.Cube(y=1, texture="assets/brick.png")
game.run()
```

If either PNG is missing, RIX creates an editable template and neutral normal
map without overwriting existing work. Defaults are 16 pixels/world-unit,
nearest filtering, automatic mapping, companion-map discovery, normal strength
1.0, and hot reload. See `examples/13_autotexture` and `features.md` for atlas,
material-map, runtime-editing, and cache details.

## Face culling

Renderable constructors accept `double_sided=True` as the simple way to draw
both sides of a surface, or `cull_mode="back" | "front" | "none"` for explicit
control:

```python
room = Cube(size=20, double_sided=True, collider=False)
portal = Plane(cull_mode="front")

room.cull_mode = "back"
portal.double_sided = True
```

The default is back-face culling. Front-face culling is useful for inward-only
shells, while `"none"` renders both sides. These settings affect rendering and
shadows only; colliders, physics, raycasts, depth testing, and mesh geometry do
not change. Imported glTF `doubleSided` metadata is honored unless the `Model`
constructor or its live renderer property supplies an explicit override.

## Multiple lights and skyboxes

```python
from rix import Game, Light, Skybox

game = Game(graphics_preset="high")
game.skybox = Skybox(top="skyblue", horizon="lightblue", bottom="#101624")
Light("point", position=(2, 3, 0), color="orange", intensity=12, range=10)
spot = Light("spot", position=(0, 7, 3), intensity=18, range=18,
             inner_angle=24, angle=48, casts_shadows=True,
             shadow_resolution=1024)
spot.look_at((0, 0, 0))
game.run()
```

Assign a 2:1 image directly with `game.skybox = "assets/sky.png"`, or use
`Skybox(cubemap="assets/sky_faces")` for right/left/top/bottom/back/front PNG
faces. Missing sky assets are generated once and never overwrite an existing
file. `None` disables the sky and `"default"` restores it. Presets bound light
and shadow work; `RendererStats` exposes active/culled lights and shadow
selection, pass, and memory counters. Run `examples/15_lighting_sky/main.py`
with `--sky procedural`, `--sky panorama`, or `--sky cubemap`.

## Testing and validation

```powershell
python -m pytest -q
python -m mypy
cmake --build --preset windows-debug
ctest --preset windows-debug
```

Automated tests validate the native core and Python contracts. Window, audio,
input-device, and visual quality checks still require an interactive Windows
desktop. See `docs/progress.md` for recorded commands and `docs/known-issues.md`
for current validation limits.

## Build and dependency policy

Dependencies are fetched at immutable commits and linked privately where
possible. The active native dependency set is SDL3, bgfx/bx/bimg, GLM,
tinyobjloader, cgltf, Jolt Physics, GameNetworkingSockets, and Protobuf. Python build tooling is pinned in
`pyproject.toml`; license details are in `LICENSES/THIRD_PARTY.md`.

The source version lives in `VERSION` and drives both the native and Python
versions. RIX is licensed under Apache License 2.0; third-party dependencies
retain their own terms, which are listed in `LICENSES/THIRD_PARTY.md`.

## Contributing and support

Runnable tutorials and examples are indexed in `docs/guides/README.md` and
`examples/`. Build and validation instructions for contributors are in
`docs/release.md`. Please include your Windows version, Python version, RIX
version, and a minimal reproduction when reporting a problem.
