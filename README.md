# Easy3D

Easy3D is a private, Windows-first 3D framework with a Python API and a C++20
native core. The current implementation includes the validated Phase 0 native
foundation, generation-safe scene/entity lifetimes, native transform
hierarchies, scene-owned cameras, and indexed solid/textured D3D11 materials
with shared PNG/JPEG and OBJ/MTL loading. Native scene render components now
power beginner-facing `Cube`, `Plane`, `Sphere`, and `Model` entities with
ambient/directional lighting and debug lines, without per-frame Python draw
submission.

The product and technical source of truth is [MASTERPLAN.md](MASTERPLAN.md).
Validation evidence and environment-specific limitations are recorded in
[docs/progress.md](docs/progress.md) and [docs/known-issues.md](docs/known-issues.md).

## Prerequisites

- Windows 10 or 11 x64
- Visual Studio Build Tools with **Desktop development with C++**, an x64 MSVC
  toolset, and a Windows 10/11 SDK. Visual Studio 2022/MSVC v143 is the intended
  minimum; the recorded Phase 0 run used Build Tools 2026/MSVC 19.51.
- CPython 3.11 x64 (3.12 and 3.13 are permitted but are not Phase 0 acceptance
  substitutes until independently validated)
- Git, CMake 3.26+, and Ninja 1.11+
- Network access on the first configure to fetch immutable dependency commits

No global vcpkg, SDL, or bgfx installation is required.

## Developer setup

Open a PowerShell prompt where the x64 MSVC compiler is available (for example
the **Developer PowerShell** installed with Visual Studio) and run from the
repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -c "import easy3d; print(easy3d.engine_version())"
python -m pytest -q
```

The editable install performs the CMake native build. A direct native build is
also available:

```powershell
cmake --preset windows-debug
cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
```

The presets use Ninja Multi-Config and therefore require `cl.exe` to be on
`PATH`. They do not install or alter global software.

## Interactive graphics smoke test

Run this only from an interactive Windows desktop session with a D3D11-capable
graphics driver:

```powershell
python examples/00_window/main.py
```

A resizable slate-blue window should appear. Resize it, then close it with the
window close control or Escape. The console logs the selected bgfx renderer and
PCI vendor/device IDs. This is a manual GPU test and is deliberately excluded
from `pytest` and CTest.

For a short visible open/close lifecycle diagnostic (still requiring a real
Windows desktop/GPU), run `python tests/manual/window_lifecycle.py`.

To exercise the Phase 1 indexed mesh path, build the native preset and run:

```powershell
cmake --build --preset windows-release --target easy3d_geometry_lifecycle
.\build\windows-release\Release\easy3d_geometry_lifecycle.exe
```

The ten-second diagnostic renders a vertex-colored triangle, solid-color cube
and UV sphere above a nearest-filtered sRGB checker-textured plane with
asymmetric UV corner markers, using
indexed GPU buffers and depth testing. It is manual
and deliberately excluded from CTest. The D3D11 shader headers are reviewed
build inputs generated from the adjacent `.sc` sources. Maintainers can rebuild
them using the pinned bgfx compiler with
`cmake --preset windows-debug -DEASY3D_REGENERATE_SHADERS=ON`.

## Scene and entity lifecycle

Entities belong to an explicit scene, either through a context or a `scene=`
argument:

```python
from easy3d import Entity, Game, Scene

world = Scene("main")
with world:
    player = Entity("player")
    prop = Entity("prop")

game = Game("My Game")
game.load_scene(world)
```

Run `python examples/01_entity_lifecycle/main.py` for creation, destruction,
stale-handle rejection, unload, and cleanup. See
[docs/api-contract.md](docs/api-contract.md) for the implemented contract.

Renderable entities use the same explicit scene ownership:

```python
from easy3d import Cube, Game, Plane, Scene

world = Scene("world")
with world:
    Plane(size=(20, 20), color=(0.25, 0.3, 0.35))
    Cube(position=(0, 0.5, 0), color=(0.2, 0.75, 0.95))

game = Game("My World")
game.load_scene(world)
game.run()
```

Run `python tests/manual/render_components.py` for the visible Phase 1.7
primitive/OBJ diagnostic or `python tests/manual/lighting_debug.py` for the
Phase 1.8 lighting, scene-camera, and native debug-line diagnostic. Public scene
mutation while `Game.run()` is accepted only from lifecycle callbacks on the
gameplay thread; other threads remain rejected during native traversal.

Run `python examples/02_first_world/main.py` for a complete Phase 1 scene with
transformed primitives, a decoded texture, loaded OBJ/MTL geometry, lights,
debug axes, and explicit teardown. Add `--seconds 5` for an automated close.

`Camera` is available as a typed perspective/orthographic configuration with
position/Euler rotation, `look_at`, basis vectors, configurable vertical FOV or
orthographic height, near/far planes, and view/projection matrix queries. Assign it with
`scene.camera = camera`. `Light("ambient", ...)` and
`Light("directional", ...)` create native light components; render entities are
lit by default and accept `lit=False` for emissive-style unlit color. Persistent
native debug lines are available through `easy3d.debug.line` and
`easy3d.debug.axes`.

The renderer conservatively culls transformed mesh bounds and hardware-instances
matching shared meshes/materials/textures when their scale is uniform. Read the
latest completed frame through `game.renderer_stats`.

## Input and action maps

Keyboard, mouse, and the primary SDL gamepad feed a thread-safe snapshot owned
by each `Game`. Bind named actions with digital controls or scaled/deadzoned
axes:

```python
from easy3d import Binding, Game

game = Game("Input example")
game.input.bind(
    "move_x",
    Binding("key:d"),
    Binding("key:a", scale=-1),
    Binding("gamepad:left_x", deadzone=0.2),
)
game.input.bind("jump", "key:space", "gamepad:a")
game.input.pointer_lock_requested = True
```

Use `state`, `value`, `down`, `pressed`, and `released` for actions. Raw helpers
cover keys, mouse buttons, gamepad buttons/axes, pointer position/delta/wheel,
focus, and gamepad identity. Focus loss clears held controls and releases active
relative mouse mode; the requested lock is restored on focus gain. Run
`python tests/manual/input_diagnostic.py --seconds 10 --pointer-lock` for a
timed native diagnostic.

## Script lifecycle and timing

Subclass any `Entity` or primitive and define the hooks you need:

```python
class Spinner(Cube):
    def awake(self):
        self.speed = 45.0

    def fixed_update(self, dt):
        pass

    def update(self, dt):
        self.rotation.y += self.speed * dt

    def on_destroy(self):
        print("removed")
```

`awake` runs once after registration, `start` once on first activation,
`fixed_update` on the fixed simulation clock, then `update` and `late_update`
once per rendered frame. Destruction and scene clear requested from a callback
commit after the current phase. `game.scheduler_stats` reports fixed ticks,
dropped catch-up time, overruns, and per-hook call timing. Development defaults
to fail-fast callback errors; pass `fail_fast=False` to quarantine a failing
script and inspect `game.script_errors`.

## Gameplay utilities

The standalone utility layer has no window, renderer, or scene dependency:

```python
from easy3d import ClockDomain, Cooldown, EventBus, StateMachine, Tween

states = StateMachine()
states.add_state("idle")
states.add_state("running", on_update=lambda dt: print(dt))
states.add_transition("idle", "running", "move")
states.start("idle")
states.trigger("move")

fire = Cooldown(0.25, time_domain=ClockDomain.SIMULATION)
events = EventBus()
hit_subscription = events.subscribe("hit", lambda damage: print(damage))
fade = Tween(0.0, 1.0, 0.5, autostart=True,
             time_domain=ClockDomain.RENDER)
```

Advance simulation timers/cooldowns from `fixed_update`, render tweens/timers
from `update`, and wall-clock objects with `poll()`. Mixing clock domains raises
instead of silently changing gameplay timing. State callbacks cannot reenter
the same machine; event listeners are synchronous, priority ordered, and safe
to add/remove while a snapshot is being dispatched.

## Physics components

Each `Scene` lazily owns an isolated Jolt Physics world. Gravity is already a
typed scene property and the scheduler advances initialized worlds exactly once
after every `fixed_update` phase:

```python
from easy3d import Collider, Entity, PhysicsMaterial, Rigidbody, Scene

scene = Scene("physics")
scene.gravity = (0, -9.81, 0)
floor = Entity("floor", scene=scene)
floor.add_component(Collider, half_extents=(5, 0.5, 5),
                    material=PhysicsMaterial(friction=0.8))

ball = Entity("ball", scene=scene)
ball.position = (0, 3, 0)
ball.add_component(Collider, shape="sphere", radius=0.5)
body = ball.add_component(Rigidbody, mass=2.0)
body.add_impulse((2, 0, 0))
```

`Cube`, `Plane`, and `Sphere` also accept `collider=True` for a matching static
collider. Add a `Rigidbody` to make it dynamic or kinematic. Distances are
meters, mass is kilograms, force is newtons, impulse is newton-seconds, and
velocity is meters/second. Dynamic transforms are solver-owned; use
`body.teleport(...)` for an explicit discontinuity. `easy3d.physics` provides
nearest/all raycasts, sphere/capsule casts, and box/sphere overlaps with layer,
trigger and entity-exclusion filters:

```python
from easy3d import physics

hit = physics.raycast(scene, (0, 2, 0), (0, -1, 0), 10)
nearby = physics.overlap_sphere(scene, (0, 0, 0), 3,
                                include_triggers=False)
```

Entity scripts can define `on_collision_enter/stay/exit(event)` and
`on_trigger_enter/stay/exit(event)`. Events are immutable snapshots dispatched
on the gameplay thread after the native fixed step; Jolt never calls Python.

PNG and JPEG assets can be validated and shared without exposing renderer
handles:

```python
from easy3d.assets import TextureCache

textures = TextureCache()
grass = textures.load("assets/grass.png", color_space="srgb")
print(grass.width, grass.height, grass.byte_size)
```

Cache keys use the canonical path and color space. Missing files raise
`MissingAssetError`; unsupported or malformed files raise `AssetError`.

OBJ/MTL metadata and immutable shared meshes use the same asset layer:

```python
from easy3d.assets import ModelCache

models = ModelCache()
tree = models.load("assets/tree.obj")
print(tree.triangle_count, len(tree.parts), len(tree.materials))
```

The initial importer triangulates faces, accepts positions/normals/UVs and
vertex colors, generates flat normals when absent, splits parts by
shape/material, and supports MTL diffuse color, dissolve, and `map_Kd`. See the
API contract for explicit MTL/path limitations.

## Benchmarks

After installation, run the small native-call harness with:

```powershell
python benchmarks/native_add.py --iterations 1000000
```

It measures Python-to-native call overhead; it is infrastructure, not an engine
performance claim.

For a visible renderer workload with frame-time distributions, process memory,
frustum counters, and instancing counters, run:

```powershell
python benchmarks/render_cubes.py --count 10000 --seconds 10
```

The benchmark validates that every requested cube is either visible or culled
and that multiple visible compatible cubes use instancing. Results are
hardware/workload measurements, not general capacity guarantees.

## Scope and license

Advanced lighting, physics, broader asset pipelines, and multiplayer systems
remain incomplete. The repository is private and
proprietary; dependencies retain the
licenses recorded in [LICENSES/THIRD_PARTY.md](LICENSES/THIRD_PARTY.md).

