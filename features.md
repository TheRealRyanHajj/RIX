# RIX feature reference

This document describes the public API implemented in the current checkout. It
is a feature and call reference, not a roadmap. RIX is now a Pygame
Community Edition-first 3D extension: Pygame owns the application, window,
event queue, clock, 2D drawing, fonts, sprites, menus, and ordinary mixer use;
RIX supplies native 3D rendering, physics, scenes, lights, models, and character
controllers. The standalone native-window API remains supported as an optional
workflow.

The package and import name are `rix`. The old `easy3d` import is only a
temporary compatibility facade that emits `DeprecationWarning`; new code should
use `import rix`.

RIX also has an optional `rix.net` multiplayer layer. Hosted matchmaking,
managed relay service, arbitrary NAT traversal, and generic rollback are not
implemented.

The supported Python versions are 3.11, 3.12, and 3.13. The repository pins
Pygame Community Edition 2.5.8 (imported as `pygame`):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[pygame,dev]"
.\.venv\Scripts\python.exe -c "import pygame, rix; print(pygame.version.ver, rix.engine_version())"
```

Use the same interpreter that performed the install. Commands in this document
can be run explicitly with `.\.venv\Scripts\python.exe`. The optional extra
installs `pygame-ce`; do not install the unrelated classic `pygame` distribution
into the same environment.

This reference was verified against RIX 0.1.0, pygame-ce 2.5.8, SDL 2.32.10,
and the current editable checkout. Pygame-facing examples below use the
application-owned `World` API; the standalone `Game` API is documented
separately because it remains supported.

## Pygame CE integration

Install the pinned optional dependency with `python -m pip install -e
".[pygame,dev]"`. `World(screen, mode="gpu")` attaches bgfx to the active
Pygame Win32 window while leaving Pygame in charge of events and timing. Pass
the `World` as the first argument to Pygame-style RIX constructors:

```python
import pygame, rix

pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)
cube = rix.Cube(
    world,
    color="orange",
    angular_velocity=(0, 45, 0),
    collider=False,
)

try:
    while world.running:
        dt_seconds = clock.tick(120) / 1000
        for event in pygame.event.get():
            world.handle_event(event)
        world.update(dt_seconds)
        world.render()
finally:
    # Release bgfx while the Pygame HWND still exists.
    world.close()
    pygame.quit()
```

`World` accepts `fixed_hz`, `max_frame_seconds`, `max_catch_up_steps`,
`fail_fast`, `graphics_preset`, `auto_setup`, `mode`, and `vsync`. It exposes
`game`, `scene`, `camera`, `input`, `lighting`, `skybox`, `renderer_stats`,
`overlay`, `mode`, `running`, and `paused`. Call `pause()`, `resume()`, `stop()`,
`handle_event(event)`, `update(dt_seconds)`, `render()`, and `close()` as shown
above. `close()` is idempotent, and `World` is also a context manager.

Features documented later through a `game` object—callback decorators,
scheduling, audio, native HUD, diagnostics, and scene switching—remain
available in a Pygame application through `world.game`. Prefer the direct
`world.scene`, `world.camera`, `world.input`, and `world.lighting` properties
when those are all that is needed:

```python
game = world.game
game.after(1.0, lambda: print("one second"))
world.lighting.ambient = 0.25
```

`handle_event()` forwards an event that the application already polled and
returns whether RIX recognized it. It never removes events from Pygame's queue.
Forwarded input includes keyboard, mouse motion/buttons/wheel, controller
buttons/axes/device changes, focus, resize, and quit. Because Pygame remains the
owner, the same event can still drive the application's own UI and
`pygame.key.get_pressed()` remains usable.

The Pygame-owned renderer currently requires Windows and a valid active Win32
display Surface. Construct, update, render, and close a `World` on the same
thread. Only one active bgfx renderer session is supported in a process.

| Concern | Pygame-owned `World` | Standalone `Game` |
| --- | --- | --- |
| Window and event queue | Pygame | RIX/SDL3 |
| Timing | `pygame.time.Clock` | RIX scheduler |
| 3D renderer and physics | RIX | RIX |
| Ordinary 2D UI | Pygame Surface overlay or Surface mode | Native RIX HUD |
| Presentation in GPU mode | RIX only | RIX only |
| Shutdown order | `world.close()`, then `pygame.quit()` | `game.close()` |

GPU mode is the default and makes RIX the sole presenter. Draw Pygame UI to a
transparent intermediate Surface, call `world.set_overlay(surface)` once, and
call `world.overlay.update(surface)` after later changes. Surface uploads are
explicit; changing the source Surface alone does not update the GPU copy. Do
not call `pygame.display.flip()` or `pygame.display.update()` in GPU mode.

`World(screen, mode="surface")` is the compatibility path for a conventional
software-composited Pygame display. Its `render()` returns an owned RGBA Pygame
Surface and does not present. Blit that Surface, draw ordinary Pygame
sprites/text, and then call `pygame.display.flip()` yourself. Full-window
`world.to_surface()` is a synchronous GPU readback and is substantially slower
than direct GPU presentation.

`Viewport(world, size=..., camera=...)` or
`Viewport(world, rect=pygame.Rect(...), camera=...)` uses a dedicated camera and
render target. It blocks only for its first default image, then uses buffered
native readback and returns the latest completed cached Surface. Pass
`blocking=True` when an immediately current viewport frame matters more than
avoiding a GPU stall. Use `refresh()`, `to_surface(refresh=True)`, and
idempotent `close()`; a viewport is also a context manager.

`SurfaceTexture(surface, srgb=True)` copies RGBA pixels immediately and exposes
`size`, `width`, `height`, `srgb`, `revision`, and `update(surface)`. Primitives
also accept a Pygame Surface directly and expose
`entity.texture.update(surface)` for explicit refreshes.
`Billboard(world, image=surface, axis="free" | "y")` creates a camera-facing,
alpha-blended world quad. Pygame `Vector2`/`Vector3` values work through RIX's
finite iterable conversion, and `Viewport` accepts Rect-compatible values.
Pygame retains input focus: route mouse/controller input to a preview
explicitly, for example with `viewport.rect.collidepoint(event.pos)`.

## Smallest complete program

```python
import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((960, 540), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)
rix.Cube(world, color="orange", angular_velocity=(0, 45, 0), collider=False)

try:
    while world.running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            world.handle_event(event)
        world.update(dt)
        world.render()
finally:
    world.close()
    pygame.quit()
```

RIX uses native C++20/bgfx D3D11 rendering and Jolt physics; it does not use
Python-side OpenGL. In this workflow Pygame, not RIX, owns the SDL window and
application loop.

## Standalone Game and frame loop

Use `Game` instead of `World` only when RIX should own a separate native SDL3
window and the main loop. This is the retained standalone workflow; it is not
required for a Pygame application.

Create a game with:

```python
from rix import Game

game = Game(
    title="RIX",
    resolution=(1280, 720),
    vsync=True,
    fps_limit=0,              # 0 means uncapped when vsync permits
    fixed_hz=60,
    max_frame_seconds=0.25,
    max_catch_up_steps=5,
    fail_fast=True,
    graphics_preset="medium", # "low", "medium", "high", or "ultra"
    auto_setup=True,
)
game.run()                    # blocks until the window closes or stop() is called
game.stop()
game.close()
```

The same scheduler also supports a manual standalone loop:

```python
import rix

with rix.Game("Manual loop") as game:
    cube = rix.Cube(color="blue", collider=False)
    while game.running:
        dt = game.tick(60)
        cube.ry += 90 * dt
```

`game.running` is the loop condition; it is initially true and becomes false
after a window-close request or `stop()`. `tick(fps=None)` initializes the
native session on first use, pumps events and input, advances the same fixed
simulation and managed callbacks as `run()`, renders/presents once, applies an
optional frame limit, and returns elapsed seconds. Code after `tick()` appears
on the next presented frame. Do not mix `run()` and `tick()` concurrently or
call `tick()` recursively. `game.is_running` specifically reports whether the
native window session is currently initialized.

With `auto_setup=True`, `Game` creates a main `Scene`, `Camera`, low ambient
light (`0.16`), an elevated warm shadow-casting key (`0.95`, shadow bias
`0.0005`), and a nearly horizontal neutral-cool fill (`0.55`) across the
opposite X/Z octant. This rig keeps top, front, and rear faces readable without
flattening them. Setting `game.lighting.directional` preserves the key/fill
ratio. The first user-authored ambient or directional light replaces all
matching defaults. `Game` exposes `game.scene`, `game.camera`, `game.lighting`,
`game.input`, and `game.audio`. It is also a context manager:

```python
with Game("Context-managed") as game:
    game.run()
```

Register variable-rate, fixed-rate, and input callbacks as decorators:

```python
@game.update
def update(dt: float) -> None:
    pass

@game.fixed_update
def fixed_update(dt: float) -> None:
    pass

@game.on_input("interact")
def interact() -> None:
    pass

@game.on_key("tab")
def toggle_menu() -> None:
    pass
```

`on_update` is an alias of `update`; `on_fixed_update` is an alias of `fixed_update`. For explicit lifetime control, use `subscribe_update`, `subscribe_fixed_update`, or `subscribe_input`. They return a `CallbackHandle` with `.active` and `.cancel()` and can be used as context managers.

Input callbacks are dispatched once on the rendered frame that observes the
press. They do not wait for a fixed physics tick, so quick interaction presses
remain reliable even when rendering faster than the 60 Hz simulation.

```python
handle = game.subscribe_update(lambda dt: print(dt))
handle.cancel()

game.after(1.0, lambda: print("once"))
repeating = game.every(0.5, lambda: print("tick"))
repeating.cancel()
```

Scene switching is explicit:

```python
from rix import Scene

level = Scene("Level 2")
game.load_scene(level)
old_scene = game.unload_scene(clear=False)
```

Runtime information is available through `game.is_running`, `game.frame_count`, `game.last_frame_seconds`, `game.graphics_preset`, `game.renderer_stats`, `game.scheduler_stats`, and `game.script_errors`.

- `RendererStats` reports draw/instance/UI/timing/texture counters plus active
  directional/point/spot lights, culled lights, shadow passes, selected/dropped
  shadow casters, and shadow memory.
- `SchedulerStats` reports `fixed_ticks`, `overrun_count`, `dropped_seconds`, and per-phase `callbacks`.
- Each `CallbackStats` contains `calls`, `total_seconds`, `max_seconds`, and `last_seconds`.
- `Lighting` provides assignable `ambient` and `directional` intensity controls for the scene's default lights.
- `GraphicsPreset` accepts the strings `"low"`, `"medium"`, `"high"`, and `"ultra"`.

## Scenes, entities, transforms, and lifecycle

`Scene` owns entities, physics, rendering data, UI, and debug lines. Use a scene as the current construction context or pass it explicitly:

```python
from rix import Entity, Scene

scene = Scene("Workshop")
with scene:
    parent = Entity("Parent")
    child = Entity("Child", parent=parent)

other = scene.create_entity("Other")
scene.destroy_entity(other)
print(scene.name, scene.entity_count, len(scene), tuple(scene.entities))
```

Important scene properties are `name`, `active`, `closed`, `world_id`, `entity_count`, `entities`, `camera`, `hud`, `gravity`, `physics_step_count`, and `debug_line_count`. `Scene.current()` returns the active construction scene. Use `clear()` to destroy all entities and `close()` for final cleanup. Entity handles are generation-checked, so a destroyed entity cannot silently refer to a later one.

Every `Entity` has local and world transforms:

```python
entity = Entity("Mover", scene=scene)
entity.position = (1, 2, 3)
entity.rotation = (0, 90, 0)       # Euler degrees
entity.scale = (2, 2, 2)
entity.x += 1
entity.ry += 45                     # continuous across full turns

print(entity.world_position, entity.world_rotation, entity.world_scale)
print(entity.quaternion, entity.world_quaternion)

entity.move((0, 0, 1), local=True)
entity.move(0, 0, 1)                 # three-number form
entity.rotate((0, 10, 0))
entity.rotate(0, 10, 0)              # three-number form
entity.look_at((0, 1, 0))
entity.teleport((5, 2, 0), rotation=(0, 180, 0))
entity.set_parent(parent, keep_world=True)
print(entity.distance_to(parent))
```

Every entity also owns native fixed-step motion state. These constructor
keywords and live properties use world units/second and degrees/second:

```python
entity = Entity(
    "Projectile",
    scene=scene,
    velocity=(0, 0, -10),
    acceleration=(0, -9.81, 0),
    angular_velocity=(0, 180, 0),
    angular_acceleration=(0, -30, 0),
)
entity.velocity.x += 1
entity.speed = 20
print(entity.speed, entity.movement_direction)
print(entity.forward, entity.right, entity.up)
entity.face_direction((1, 0, -1))
entity.launch((1, 0.25, -1), 40, face=True)
entity.teleport((0, 5, 0), reset_motion=True)
```

`local_to_world_direction()` and `world_to_local_direction()` convert vectors
through the world rotation. Motion remains world-space for parented entities.
Velocity never changes facing implicitly. Disabling freezes motion and
re-enabling restores it. Collider-only static entities reject nonzero motion;
use a kinematic Rigidbody for moving collision geometry.

The local `rotation`/`rx`/`ry`/`rz` facade remembers explicitly authored
Euler angles while the native transform remains quaternion-backed. Repeated
operations such as `entity.ry += speed * dt` therefore pass through 90°, 180°,
360°, and additional turns without folding at quaternion Euler singularities.
If native physics or an explicit `quaternion` assignment changes orientation,
the facade detects it and adopts the new native rotation.

Other state and hierarchy members are `id`, `scene`, `is_alive`, `name`, `enabled`, `visible`, `parent`, and `children`. Call `show()`, `hide()`, `enable()`, `disable()`, `destroy()`, or `destroy_after(seconds)` as needed.

Subclass `Entity` for script lifecycle hooks:

```python
class Spinner(Entity):
    def awake(self) -> None:
        pass

    def start(self) -> None:
        pass

    def fixed_update(self, dt: float) -> None:
        pass

    def update(self, dt: float) -> None:
        self.rotate((0, 60 * dt, 0))

    def late_update(self, dt: float) -> None:
        pass

    def on_destroy(self) -> None:
        pass

spinner = Spinner("Spinner")
```

Scene mutations requested inside callbacks are deferred safely. Callback failures are recorded as diagnostic strings in `game.script_errors`; `fail_fast=True` raises `ScriptCallbackError` immediately.

## Built-in geometry and models

The convenience entities are `Cube`, `Sphere`, `Plane`, and `Model`:

```python
from rix import Cube, Model, Plane, Sphere

floor = Plane(
    position=(0, 0, 0), rotation=(0, 0, 0), size=(30, 30),
    color="gray", texture=None, lit=True, collider=True,
    friction=0.8, bounciness=0.0, collision_layer="static",
)

box = Cube(
    position=(0, 3, 0), rotation=(0, 30, 0), size=(1, 2, 1),
    color="#ff8800", texture=None, lit=True,
    collider=True, physics=True, mass=2.0, gravity=True,
    friction=0.3, bounciness=0.1, continuous=False, kinematic=False,
)

ball = Sphere(
    position=(2, 3, 0), radius=0.5, color=(0.2, 0.6, 1.0, 1.0),
    collider=True, physics=True,
)

ship = Model(
    "assets/ship.glb", position=(0, 0, -4), rotation=(0, 180, 0),
    scale=1.0, color="white", lit=True, collider="convex",
)
```

In a Pygame application, pass the `World` positionally so the object is placed
in that world's scene:

```python
cube = rix.Cube(world, position=(0, 0.5, 0), color="orange")
ball = rix.Sphere(world, position=(2, 1, 0), physics=True)
floor = rix.Plane(world, y=0, size=30)
model = rix.Model(world, "assets/ship.glb", position=(0, 0, -4))
player = rix.Player(world, position=(0, 0.1, 5))
```

`Cube`, `Sphere`, `Plane`, `Model`, `Player`, and `Billboard` accept this
Pygame-oriented first positional `world`. Other scene objects use the active
scene created by `World`, or can be made explicit with `scene=world.scene`.

`Cube`, `Sphere`, `Plane`, `Model`, and `Billboard` create colliders by default.
Pass `collider=False` for decoration, parented visuals, or ordinary entities
moved by universal motion rather than a kinematic rigid body. `Model()` uses a
triangle-mesh collider by default; `collider=True` is its shorthand for
`"mesh"`, while `"convex"` selects a convex shape.

All four accept `name`, `parent`, `scene`, and the four universal motion
vectors; transform shortcuts `x`, `y`, `z`, `rx`, `ry`, and `rz` are
supported. `Light`, `Player`, `Enemy`, and `DebugOverlay` accept the same
motion vectors. `Model.collider` can be `False`, `True`, `"mesh"`, or `"convex"`.
Primitive `trigger` may be a boolean or a callback. Colors accept `black`,
`white`, `red`, `green`, `blue`, `yellow`, `orange`, `purple`, `pink`, `cyan`,
`gray`/`grey`, `#RRGGBB`, `#RRGGBBAA`, or float RGB/RGBA tuples.

## Components and materials

Components can be constructed directly or through an entity:

```python
from rix import Collider, MeshRenderer, PhysicsMaterial, Rigidbody

entity = Entity("Crate")
renderer = entity.add_component(MeshRenderer)
collider = entity.add_component(
    Collider,
    shape="box",
    half_extents=(0.5, 0.5, 0.5),
    trigger=False,
    layer="dynamic",
    material=PhysicsMaterial(friction=0.4, restitution=0.1),
)
body = entity.add_component(
    Rigidbody, body_type="dynamic", mass=1.0, use_gravity=True, continuous=False
)

print(entity.has_component(Collider))
print(entity.get_component(Rigidbody))
entity.remove_component(MeshRenderer)
```

`MeshRenderer` exposes `kind`, `color`, `asset`, `lit`, `metallic`, `roughness`, `emission`, `casts_shadows`, `receives_shadows`, `cull_mode`, and `double_sided`. These surface properties are assignable. Call `remove()` to detach the component.

Face visibility is explicit and does not modify physics geometry:

```python
room = Cube(size=20, double_sided=True, collider=False)
inward_shell = Sphere(radius=10, cull_mode="front")

room.cull_mode = "back"       # discard back-facing triangles
inward_shell.double_sided = True  # equivalent to cull_mode="none"
```

`CullMode` is the public literal type `"back" | "front" | "none"`. The
default for primitives and OBJ models is `"back"`. `double_sided=True` means
`"none"`, and `False` means `"back"`; passing incompatible values for both
constructor arguments raises `ValueError`. Runtime entity and renderer
properties reference the same native component, so changing either view is
immediately visible through the other.

For `Model`, explicit constructor/runtime state overrides every part, otherwise
glTF material `doubleSided` is honored per part and missing metadata falls back
to back culling. Cull mode is part of the native instancing key and follows the
same policy in the shadow pass. Mirrored transforms preserve the intended side,
and two-sided normal-mapped lighting reverses the complete shading normal for
back fragments. Culling is separate from depth testing and does not affect
colliders, contacts, queries, or raycasts.

`Collider` supports `shape="box"`, `"sphere"`, `"capsule"`, `"convex"`, or `"mesh"`; shape data is supplied with `half_extents`, `radius`, `height`, `points`, or `mesh`. Its readable properties are `entity`, `shape`, `half_extents`, `radius`, `height`, `is_trigger`, `layer`, and `material`. Collision layers are `"static"`, `"dynamic"`, `"sensor"`, and `"character"`. `PhysicsMaterial` contains `friction` and `restitution`.

For annotations, `rix.physics` also exports the literal aliases `CharacterMode`, `ColliderShape`, `CollisionLayer`, `ConstraintType`, and `RigidBodyType`.

`Rigidbody` supports dynamic and kinematic bodies:

```python
body.linear_velocity = (0, 2, 0)
body.angular_velocity = (0, 90, 0)  # degrees/second at the Python boundary
body.add_force((10, 0, 0))
body.add_impulse((0, 5, 0))
body.teleport((0, 10, 0), rotation=(0, 45, 0))
body.remove()
```

## Character controller and ready-made player

`CharacterController` provides native ground detection, slope and step handling,
Source-style projection acceleration, ground friction, edge-triggered jumping,
sprinting, and crouching. It deliberately has no coyote time, jump buffer, or
held-jump auto-hop:

```python
from rix import CharacterController

controller = entity.add_component(
    CharacterController,
    mode="first_person",        # or "third_person"
    radius=0.4,
    height=1.8,
    speed=5.0,
    acceleration=30.0,
    air_acceleration=8.0,
    ground_friction=6.0,
    stop_speed=1.0,
    air_speed_cap=1.5,
    horizontal_speed_limit=None,  # optional total cap; None permits bhop gain
    jump_speed=5.0,
    max_slope_degrees=50.0,
    step_height=0.4,
    sprint_multiplier=1.6,
    crouch_height=1.2,
    crouch_speed_multiplier=0.5,
)
controller.set_input((0, 0, 1), heading_degrees=90, jump=True, sprint=True, crouch=False)
controller.teleport((0, 2, 0), heading_degrees=0)
controller.linear_velocity = (2, 0, 0)
print(controller.grounded, controller.crouched, controller.sprinting)
print(controller.linear_velocity, controller.ground_normal)
```

The controller also exposes its configured `entity`, `mode`, `radius`, `height`,
`speed`, `acceleration`, `air_acceleration`, `ground_friction`, `stop_speed`,
`air_speed_cap`, `horizontal_speed_limit`, `jump_speed`, `max_slope_degrees`,
`step_height`, `sprint_multiplier`, `crouch_height`, and
`crouch_speed_multiplier`. Call `remove()` to detach it. Input is normalized, so
diagonal ground movement is not faster. In air, only the velocity projection
along the requested direction is capped; perpendicular strafing can curve and
gain total speed. A jump pressed on the first grounded landing tick skips ground
friction and preserves momentum, while holding Space does not jump again.

`Player` combines an entity, character controller, camera rig, and optional default input bindings:

```python
from rix import Player

player = Player(
    position=(0, 1, 5),
    controller="first_person",
    move_speed=5.0,
    move_acceleration=30.0,
    air_acceleration=8.0,
    ground_friction=6.0,
    air_speed_cap=1.5,
    jump_speed=5.8,
    sprint_multiplier=1.6,
    crouch_height=1.2,
    controls=True,
    mouse_sensitivity=0.1,
    sprinting=True,
    crouching=True,
    camera_height=1.55,
    third_person_distance=5.0,
)
player.set_controls_enabled(True)
player.move((0, 0, 1), heading_degrees=0, jump=False, sprint=True, crouch=False)
print(player.forward, player.view_forward)
```

`Player(y=2)` and the other `x`/`y`/`z` shortcuts are accepted when
`position` is omitted.

`Player(speed=...)` and scalar `Player(acceleration=...)` are intentionally
removed and raise migration errors. Use `move_speed`/`move_acceleration` for
character tuning; vector `velocity`/`acceleration` are universal entity motion.
The controller's own `speed` and `acceleration` names are unchanged.

Default controls are WASD/arrow keys and gamepad left stick for motion, Space/gamepad A for jump, Shift for sprint, Ctrl for crouch, left click for pointer capture, and Escape for release. Q and E no longer rotate the player. Q, E, and Tab remain available to custom bindings through `Input` and `Game.on_key`.

The built-in player latches a render-frame jump press until one fixed physics
tick consumes it, then clears the request. Jumping is edge-triggered: holding
Space/gamepad A does not automatically jump again on landing. A correctly timed
press on the first grounded landing tick skips ground friction and preserves
incoming horizontal momentum for bunny hopping. Air movement uses
projection-based acceleration without implicit horizontal drag, allowing
Source-style air strafing. Native action state also preserves both edges of a
press-and-release that arrives within one polled frame.

## Input

`game.input` is an `Input` object. Bind named actions to keyboard, mouse, and gamepad controls:

```python
from rix import Binding

game.input.bind("forward", "key:w", Binding("gamepad:left_y", scale=-1, deadzone=0.2))
game.input.bind("menu", "key:tab")
game.input.bind("ability_q", "key:q")
game.input.bind("ability_e", "key:e")

state = game.input.state("forward")
print(state.value, state.down, state.pressed, state.released)
print(game.input.value("forward"), game.input.down("menu"))
print(game.input.pressed("menu"), game.input.released("menu"))

print(game.input.key("space"))       # physical key held
print(game.input.pressed("e"))       # action if bound, otherwise key edge
print(game.input.mouse("left"))      # physical mouse button held

game.input.unbind("ability_q")
game.input.clear_actions()
```

Use `bindings(action)` to inspect an action. Raw accessors are `key_down(key)`, `mouse_button_down(button)`, `gamepad_button_down(button)`, and `gamepad_axis(axis)`. `game.input.pointer` returns a `PointerState(position, delta, wheel)`. Other properties are `focused`, `pointer_lock_requested` (assignable), `pointer_locked`, `gamepad_connected`, and `gamepad_name`. `Binding` contains `control`, `scale`, and `deadzone`; `ActionState` contains `value`, `down`, `pressed`, and `released`.

Physical edge helpers are `key_pressed`, `key_released`, `mouse_pressed`, and
`mouse_released`. Use `@game.on_mouse("left")` for a mouse-button decorator,
parallel to `@game.on_key("space")`.

## Camera, lights, and renderer features

Create and assign cameras explicitly when needed:

```python
from rix import Camera

camera = Camera(
    position=(0, 3, 8), rotation=(0, 0, 0),
    vertical_fov_degrees=60, near_plane=0.1, far_plane=1000,
    projection="perspective",   # or "orthographic"
    orthographic_height=10,
)
camera.look_at((0, 1, 0))
game.scene.camera = camera
print(camera.forward, camera.right, camera.up, camera.quaternion)
print(camera.view_matrix())
print(camera.projection_matrix((1280, 720)))
print(Camera.aspect_ratio((1280, 720)))
```

`Projection` is the `"perspective" | "orthographic"` type. All camera construction properties are readable and assignable.

Lighting uses native ambient, directional, point, and spot lights. Lights are
normal entities, so position, rotation, parenting, `enabled`, and `look_at()`
remain live:

```python
from rix import Light, LightComponent

sun = Light("directional", color="white", intensity=1.2, rotation=(-45, -30, 0))
fill = Light("ambient", color=(0.3, 0.35, 0.45, 1), intensity=0.35)
lamp = Light("point", position=(2, 3, 0), color="orange", intensity=10, range=8)
spot = Light("spot", position=(0, 6, 3), range=15, inner_angle=20, angle=45,
             casts_shadows=True, shadow_resolution=1024, shadow_bias=0.002)
spot.look_at((0, 0, 0))
sun.color = "yellow"
sun.intensity = 1.0
game.lighting.ambient = 0.3
game.lighting.directional = 1.0

component = sun.get_component(LightComponent)
print(component.kind, component.color, component.intensity, component.range)
```

The automatic key/fill rig is only a beginner default. Its elevated key avoids
an ambient-only top face, its near-horizontal fill preserves detail on the rear
X/Z faces, and the reduced directional bias keeps contact shadows attached to
grounded objects. Creating the first explicit directional light removes both
default directionals; creating an explicit ambient light removes the default
ambient source. Directional-light position is irrelevant—use rotation,
`look_at()`, or `face_direction()` to change its direction.

Directional/point/spot budgets are low `1/4/2`, medium `2/16/8`, high
`4/32/16`, and ultra `4/64/32`. Local lights outside the camera frustum are
discarded before deterministic shadow-first/relevance ordering. High/ultra can
select one directional, one spot, and one point shadow caster; a point shadow
uses six cubemap passes. Solid, textured, model, instanced, normal/PBR-map,
emissive, and two-sided material paths share the same lighting arrays.

Each scene also owns a skybox:

```python
from rix import Skybox

game.skybox = Skybox(top="skyblue", horizon="lightblue", bottom="#101624")
game.skybox = "assets/panorama.png"             # equirectangular 2:1
game.skybox = Skybox(cubemap="assets/cubemap") # six named PNG faces
game.skybox.rotation += 15
game.skybox.brightness = 1.25
game.skybox = None                              # disable
game.skybox = "default"                        # restore procedural
```

Missing panorama paths generate a bounded 2048x1024 PNG. Missing cubemap
folders/faces generate bounded 512x512 `right`, `left`, `top`, `bottom`,
`back`, and `front` PNGs. Exclusive creation never replaces an existing asset.
The sky is translation-invariant, responds to camera/sky rotation, draws behind
geometry, and shares the scene post-process/FXAA target. Availability depends
on the active D3D11 device; inspect `game.renderer_stats`. There is no public
dithering-light feature.

## Physics simulation, queries, constraints, and events

Set world gravity through the scene:

```python
game.scene.gravity = (0, -9.81, 0)
```

Queries live in the `rix.physics` module and return `PhysicsHit` objects:

```python
from rix import Vec3, physics

hit = physics.raycast(
    game.scene, origin=(0, 10, 0), direction=(0, -1, 0), max_distance=100,
    layers=("static", "dynamic"), include_triggers=False, exclude=player,
)
if hit is not None:
    print(hit.entity, hit.point, hit.normal, hit.distance, hit.fraction)

all_hits = physics.raycast_all(game.scene, (0, 10, 0), (0, -1, 0), 100)
nearby = physics.overlap_sphere(game.scene, (0, 0, 0), 5)
inside_box = physics.overlap_box(
    game.scene, (0, 1, 0), (2, 1, 2), rotation=(0, 0, 0)
)
sphere_hit = physics.sphere_cast(game.scene, (0, 1, 0), 0.5, (1, 0, 0), 20)
sphere_hits = physics.sphere_cast_all(game.scene, (0, 1, 0), 0.5, (1, 0, 0), 20)
capsule_hit = physics.capsule_cast(game.scene, (0, 1, 0), 0.4, 1.8, (1, 0, 0), 20)
capsule_hits = physics.capsule_cast_all(game.scene, (0, 1, 0), 0.4, 1.8, (1, 0, 0), 20)
```

Beginner shortcuts supply the scene and viewpoint:

```python
hit = game.raycast((0, 1, 0), (0, 0, -1), distance=10)
hit = entity.raycast(10)  # entity position and forward direction
hit = player.raycast(20, layers=("static", "dynamic"))  # active camera
```

Every query accepts layer filtering, trigger inclusion, and an excluded entity. `overlap_box` and capsule casts also accept rotation.

Create fixed and distance constraints:

```python
fixed = physics.fixed_constraint(first_entity, second_entity)
rope = physics.distance_constraint(
    first_entity,
    second_entity,
    first_anchor=(0, 0, 0),
    second_anchor=(0, 0, 0),
    minimum_distance=1,
    maximum_distance=5,
)
print(rope.type, rope.first, rope.second, rope.is_alive)
rope.remove()
```

Receive collision or trigger callbacks on entity subclasses:

```python
class Target(Entity):
    def on_collision_enter(self, event) -> None:
        print(event.other, event.point, event.normal)

    def on_collision_stay(self, event) -> None:
        pass

    def on_collision_exit(self, event) -> None:
        pass

    def on_trigger_enter(self, event) -> None:
        pass
```

Or register them centrally:

```python
@game.on_collision(box, phase="enter", trigger=False)
def collided(event) -> None:
    print(event.other)
```

The event value is `CollisionEvent(other, point, normal)`. `Constraint` and `PhysicsHit` are the returned value types. Invalid physics operations raise `PhysicsError`.

## Assets, textures, models, skeletons, and animation metadata

Load image metadata and shared native texture resources:

```python
from rix import TextureCache, load_image

info = load_image("assets/crate.png", color_space="srgb") # or "linear"
print(info.path, info.width, info.height, info.byte_size, info.color_space)

textures = TextureCache()
textures.load("assets/crate.png")
print(len(textures))
textures.clear()
```

### AutoTexture and advanced materials

Only a filename is required. Missing local PNGs and a matching neutral normal
template are generated automatically. In the Pygame-owned workflow, create the
objects in the active `World` and keep Pygame's loop in control:

```python
import pygame
import rix

pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)

ground = rix.Plane(world, size=40, texture="assets/grass.png")
crate = rix.Cube(world, texture="assets/crate.png", texture_mode="atlas")
ball = rix.Sphere(world, texture="assets/planet.png")

try:
    while world.running:
        dt = clock.tick(120) / 1000.0
        for event in pygame.event.get():
            world.handle_event(event)
        world.update(dt)
        world.render()
finally:
    world.close()
    pygame.quit()
```

Automatic mode tiles cubes/planes, uses spherical UVs for spheres, and preserves
authored OBJ/glTF UVs. The cube atlas is a deterministic cross with front,
back, right, left, top, and bottom regions. Generated files have a
`.texture.json` sidecar; incompatible reuse raises `AssetError` and no existing
image is overwritten. Atlas regions remain bound to the dimensions that created
the PNG, so later scalar, nonuniform, mirrored, or parent scaling cannot move a
face into another atlas region. Tile and sphere density continue to use live
world dimensions.

If an RIX-generated base/normal PNG pair is deleted but its sidecars remain,
the complete retained identity is checked before either image is recreated.
Compatible RIX sidecars are refreshed; incompatible or malformed metadata
fails without leaving a partial pair, and user-owned metadata is not rewritten.

Per-object overrides work in both workflows. The global constructor defaults
shown here belong to the optional standalone `Game` workflow:

```python
game = rix.Game(
    pixels_per_unit=32,
    texture_filter="linear",       # default: "nearest"
    texture_mode="tile",           # default: "auto"
    texture_hot_reload=False,       # default: True
)
wall = e3.Cube(
    texture="brick.png",
    pixels_per_unit=16,
    normal_map="brick_normal.png", # None discovers _normal; False disables it
    roughness_map="brick_roughness.png",
    metallic_map="brick_metallic.png",
    emissive_map="brick_emissive.png",
    ambient_occlusion_map="brick_ao.png",
    normal_strength=0.75,
    roughness=0.8,                 # optional map multiplier
    metallic=0.25,                # optional map multiplier
    emission=1.5,                 # optional map multiplier
)
```

Albedo/emissive maps use sRGB; normal/roughness/metallic/AO maps use linear
sampling. Scalar roughness, metallic, and emission multiply their corresponding
map values. When one of those maps is discovered and its scalar is omitted, the
constructor uses the neutral multiplier `1`; without a map, legacy defaults are
roughness `0.5`, metallic `0`, and emission `0`. Explicit scalar arguments always
win. glTF packed metallic-roughness uses the standard green/blue channels. All
maps are optional.

Primitive material settings are live through `MeshRenderer`:

```python
renderer = wall.get_component(e3.MeshRenderer)
assert renderer is not None
renderer.texture = "paint.png"
renderer.texture_mode = "tile"
renderer.pixels_per_unit = 24
renderer.texture_filter = "nearest"
renderer.normal_strength = 1.25
renderer.normal_map = False
```

`TextureCache.poll_changes()` performs an immediate explicit poll. The renderer
polls enabled local resources no more frequently than every 250 ms, keeps the
last valid image during a partial/invalid save, and updates every object sharing
the cached image after a valid save. Destroying/clearing the final scene owner
releases the corresponding GPU handles after a safe rendered frame.

Load OBJ/MTL, glTF 2.0/GLB, or FBX metadata:

```python
from rix import ModelCache, load_fbx, load_gltf, load_obj

obj = load_obj("assets/level.obj")
gltf = load_gltf("assets/character.glb")
fbx = load_fbx("assets/YBot.fbx")
print(obj.triangle_count, obj.parts, obj.materials, obj.warnings)
print(gltf.skeleton, gltf.animations, fbx.skeleton)

models = ModelCache()
models.load("assets/level.obj")
print(len(models))
models.clear()
```

`ImageInfo`, `ModelInfo`, `GltfInfo`, `ModelPartInfo`, and `ModelMaterialInfo` are immutable metadata records. Materials report diffuse color/texture, metallic, roughness, emission, and imported `double_sided` state. A `GltfInfo` can also contain:

- `SkeletonInfo(name, joints)` and `SkeletonJointInfo(name, parent, bind_position, bind_rotation, bind_scale, inverse_bind)`.
- `AnimationClipInfo(name, duration, channels)` and `AnimationChannelInfo(joint_index, target, interpolation, times, values)`.
- `JointPose(position, rotation, scale)` returned by `clip.sample(skeleton, seconds, loop=True)`.

### FBX skeletal animation

FBX and glTF share one native skeleton, clip, controller, blending, and skinning
runtime. Playback is automatic on the scene scheduler:

```python
character = rix.Model("assets/YBot.fbx", collider=False)
character.add_animation("Thriller", "assets/Thriller Animation.fbx")
character.play("Thriller", loop=True, speed=1.0, blend=0.15)

print(character.animation_clips)
print(character.current_animation, character.animation_time)
print(character.animation_duration, character.animation_state)
print(character.animation_skinning)  # "gpu" (<=64 joints) or "cpu"

character.pause_animation()
character.resume_animation()
character.stop_animation()
```

`play(..., speed=-1)` runs in reverse. `play(..., loop=False,
on_complete=callback)` invokes the callback once. `root_motion=False` is the
in-place default; explicit root motion drives the owner's horizontal X/Z
translation and yaw while authored vertical hip motion and pitch/roll remain in
the skeleton. It is rejected where dynamic/character/static-collider physics
owns the transform. Each `Model` has independent time/pose while immutable
cached data is shared.

The D3D11 renderer skins position, normal, and tangent attributes and uses the
same palette for directional/spot/point shadows. Four influences are retained.
Rigs through 64 joints use GPU uniforms; larger rigs use bounded native CPU
skinning once per model part per frame, shared by the main and shadow passes.
See `docs/fbx-importing.md`, `docs/skeletal-animation.md`, and
`docs/animation-retargeting.md` for supported FBX material/texture fallbacks,
Mixamo attachment, Pygame usage, and compatibility limits.

## Audio

Pygame applications normally continue using `pygame.mixer.Sound` and the
existing Pygame mixer setup. The standalone RIX path also includes a native WAV
manager accessed through `game.audio`:

```python
sound = game.audio.load("assets/jump.wav")
source = game.audio.play(sound, volume=0.8, loop=False)
spatial = game.audio.play(
    sound,
    volume=1.0,
    loop=True,
    position=(0, 2, -5),
    minimum_distance=1.0,
    maximum_distance=50.0,
)

print(sound.path, sound.channels, sound.sample_rate, sound.frame_count, sound.duration)
print(source.playing, source.loop, source.spatial)
source.volume = 0.5
source.position = (2, 1, 0)
source.stop()
print(game.audio.available, game.audio.sound_count, game.audio.active_voice_count)
```

For ordinary effects, load and play through the same cache in one call:

```python
game.play_sound("assets/jump.wav", volume=0.8)
game.play_sound("assets/explosion.wav", position=enemy.position)
```

`Audio`, `Sound`, and `AudioSource` are the corresponding public types. The current loader is for WAV audio.

## Native HUD and UI layout

For a Pygame-owned `World`, ordinary Pygame Surfaces, fonts, sprites, and menus
are the primary UI path; upload them with `world.set_overlay()` in GPU mode or
draw them normally after the 3D blit in Surface mode. The retained native UI
below is available for standalone `Game` projects and through
`world.scene.hud` when deliberately desired.

Each scene has a retained, native-rendered `HUD` at `scene.hud`:

```python
hud = game.scene.hud
panel = hud.panel(position=(20, 20), size=(300, 140), anchor="top_left")
label = hud.text("Score: 0", position=(40, 40), font_size=24)
icon = hud.sprite("assets/icon.png", position=(40, 80), size=(48, 48))
button = hud.button(
    "Start",
    on_click=lambda button: print("clicked"),
    position=(0, 0),
    size=(180, 48),
    anchor="center",
)
print(hud.elements)
```

The same elements have direct convenience constructors using `x`, `y`, `width`, `height`, `anchor`, and optional `scene`:

```python
from rix import Button, Image, Panel, Sprite, Text

Panel(x=20, y=20, width=300, height=100, color=(0, 0, 0, 0.8))
Text("Hello", x=30, y=30, font_size=28, color="white")
Sprite("assets/icon.png", x=30, y=65, width=48, height=48)
Image("assets/photo.png", x=100, y=65, width=96, height=48) # Sprite alias
Button("Continue", click=lambda: print("continue"), x=0, y=0, anchor="center")
```

Every `UIElement` exposes `id`, `removed`, `kind`, `anchor`, `position`, `size`, `color`, `text`, `text_color`, `font_size`, `z_index`, `visible`, and `enabled`; mutable visual properties can be assigned. Call `remove()` to delete an element or `hud.clear()` to delete all of them. Anchors are `top_left`, `top`, `top_right`, `left`, `center`, `right`, `bottom_left`, `bottom`, and `bottom_right`.

Compose layout with `Stack`, `Row`, `Column`, and `Grid`:

```python
from rix import Column, Grid, Row, Stack

row = Row(label, button, x=0, y=0, anchor="center", spacing=12, padding=8)
column = Column(label, button, anchor="left", gap=10, alignment="start")
stack = Stack("vertical", anchor="center", spacing=8, padding=6, margin=2)
stack.add(label, button).relayout()

grid = Grid(columns=2, x=20, y=20, anchor="top_left", gap=8, padding=4)
grid.add(label, button)
grid.relayout()
print(row.size, column.size, grid.size)
```

`Stack` directions are `horizontal` and `vertical`; alignment is `start`, `center`, or `end`.

Use data-bound convenience widgets:

```python
from rix import HealthBar, ProgressBar, ScoreboardPanel

progress = ProgressBar(0.65, x=20, y=20, width=220, height=24)
progress.value = 0.8
health_bar = HealthBar(health, x=20, y=52)
score_panel = ScoreboardPanel(scoreboard, x=20, y=20, anchor="top_right")
score_panel.sync()
score_panel.relayout()
```

## Local gameplay helpers

### Health and damage

```python
from rix import Health

health = Health(entity, maximum=100, current=75, invulnerable=False)
assert Health.for_entity(entity) is health
health.on_damage(lambda event: print(event.amount, event.source))
health.on_death(lambda event: print(event.target))
health.on_change(lambda value: print(value.current, value.fraction))
damage_event = health.damage(20, source=attacker)
health.heal(10)
health.reset()
print(health.current, health.maximum, health.alive, health.fraction)
```

The equivalent attached form reuses that same `Health` implementation:

```python
player.add_health(100)
player.health.damage(20)
player.health.heal(10)
```

Damage callbacks receive `DamageEvent(target, amount, previous, current, source)`; death callbacks receive `DeathEvent(target, source)`.

### Spawn and respawn

```python
from rix import Respawner, SpawnPoint

points = [
    SpawnPoint((0, 1, 0), rotation=(0, 0, 0), team="blue", name="Blue spawn"),
    SpawnPoint((10, 1, 0), rotation=(0, 180, 0), team="red", name="Red spawn"),
]
respawner = Respawner(points, seed=123)
point = respawner.choose(team="blue")
respawner.respawn(player, health=health, point=point)
```

### Scores and local teams

```python
from rix import Scoreboard, Team, TeamRoster

scores = Scoreboard()
scores.add_player("Ryan", score=0)
scores.add("Ryan", 5)
print(scores.score("Ryan"), scores.ranking)
scores.on_change(lambda board: print(board.ranking))
scores.remove_player("Ryan")

red = Team("red", color="red")
blue = Team("blue", color="blue")
roster = TeamRoster(red, blue)
assigned = roster.assign(player, roster.smallest())
print(roster.team_of(player), roster.members(assigned))
roster.remove(player)
```

State machines are local unless an application explicitly connects them to
`rix.net` replicated match state; local menus and pause overlays are never
networked automatically.

### Hitscan weapons, interaction, and enemies

```python
from rix import Enemy, HitscanWeapon, Interaction

weapon = HitscanWeapon(player, damage=25, range=50, cooldown=0.2)
weapon.advance(dt)
if weapon.ready:
    result = weapon.fire(player.world_position, game.camera.forward)
    if result is not None:
        print(result.hit, result.damage)

door_use = Interaction(door, lambda actor: door.hide(), distance=2.5)
door_use.interact(player)

enemy = Enemy(
    health=100,
    speed=3,
    behavior="chase", # or "idle"
    target=player,
    stop_distance=1.25,
    color="red",
    position=(0, 1, -8),
)
```

Weapon fire returns a `ShotResult(hit, damage)` when a shot is accepted; cooldown can make `fire()` return `None`. `rix.gameplay.EnemyBehavior` is the public `"idle" | "chase"` annotation alias.

For a camera-aimed, automatically advanced player weapon:

```python
player.add_weapon(damage=25, cooldown=0.3, range=50)

@game.on_mouse("left")
def shoot() -> None:
    player.weapon.fire()
```

## Math types

`Vec2` and `Vec3` accept individual numbers or iterables and support iteration, addition, subtraction, scalar multiplication/division, `length`, `length_squared`, normalization, dot products, and approximate comparison. `Vec3` also supports negation, cross products, and `Vec3.from_value(value)` for copying a vector-compatible value.

```python
from rix import Quat, Vec2, Vec3

uv = Vec2(1, 2)
position = Vec3(1, 2, 3)
direction = Vec3((0, 0, 1)).normalized()
print(position + direction * 5, position.dot(direction))
print(Vec3(1, 0, 0).cross(Vec3(0, 1, 0)))

rotation = Quat.from_euler((0, 90, 0))
rotated = rotation.rotate((0, 0, 1))
print(rotation.normalized(), rotation.conjugate(), rotation.to_euler(), rotated)
```

`Quat(w, x, y, z)` supports construction from a four-value iterable, quaternion multiplication, normalization, conjugation, vector rotation, `from_euler`, `to_euler`, iteration, and `almost_equal`.

## Timers, state machines, events, cooldowns, and tweens

Time-aware utilities use a `ClockDomain`: `ClockDomain.SIMULATION`, `ClockDomain.RENDER`, or `ClockDomain.WALL`.

```python
from rix import ClockDomain, Timer

timer = Timer(
    1.0,
    repeat=True,
    autostart=True,
    time_domain=ClockDomain.SIMULATION,
    callback=lambda: print("timer"),
)
fired_count = timer.advance(dt, time_domain="simulation")
timer.pause()
timer.resume()
timer.reset(start=True)
timer.cancel()
```

For wall-clock timers, call `poll()` instead of `advance()`. Properties include `duration`, `repeat`, `time_domain`, `running`, `finished`, `cancelled`, `elapsed`, `remaining`, `progress`, and `completions`.

```python
from rix import Cooldown

cooldown = Cooldown(0.25)
if cooldown.trigger():
    fire()
cooldown.advance(dt)
print(cooldown.ready, cooldown.remaining)
cooldown.cancel()
```

Wall-domain cooldowns use `poll()`. `trigger(restart=False)` starts only when ready.

```python
from rix import State, StateMachine, Transition

machine = StateMachine()
machine.add_state(State("idle", on_update=lambda dt: None))
machine.add_state("running", on_enter=lambda previous: print(previous))
machine.add_transition("idle", "running", "move", guard=lambda: True)
machine.start("idle")
machine.trigger("move")
machine.update(dt)
machine.transition_to("idle")
machine.stop()
print(machine.current, machine.previous, machine.time_in_state, machine.states, machine.running)
```

`State` stores `name`, `on_enter`, `on_update`, and `on_exit`; `Transition` stores `source`, `target`, `event`, and optional `guard`.

The shorter decorator API supports deferred transitions from callbacks,
conditions, priorities, and state-owned timers:

```python
machine = StateMachine("idle")

@machine.state("idle")
def idle(dt: float) -> None:
    if enemy_visible():
        machine.change("chase")

@machine.state("chase")
def chase(dt: float) -> None:
    move_toward_enemy(dt)

@machine.enter("chase")
def began_chasing(previous: str | None) -> None:
    print("entered from", previous)

machine.when("chase", "idle", condition=lambda: not enemy_visible(), priority=10)
machine.after(5.0, "idle", state="chase")
machine.update(dt)
```

`change()` is safe inside callbacks and commits after the active callback.
Conditions use descending priority and stable registration order, with a
bounded transition count. The initial state starts on the first update, after
all decorators are registered. An entity owned by a `Game` can create an
automatically managed machine with `entity.state_machine("idle")`.

Every entity exposes `entity.animations`, an `AnimationSelection` state holder.
`play("run")` selects a clip name without restarting an unchanged selection;
`play("run", restart=True)` increments the playback revision explicitly.
`@machine.state("run", animation="run")` updates that selection when the state
becomes active. This is currently clip-selection/runtime intent only: imported
glTF animation metadata can be sampled, but the renderer still draws the base
pose and does not claim GPU-skinned playback.

`GameStates` manages Pygame-friendly screens and overlay stacks:

```python
from rix import GameStates

screens = GameStates("menu")

@screens.screen("menu")
class Menu:
    def event(self, event: object) -> None: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: object) -> None: ...

screens.change("playing")
screens.push("pause")
screens.pop()
screens.after(2.0, "menu")
screens.event(event)
screens.update(dt)
screens.draw(surface)
```

Only the top screen receives events and updates; `draw()` traverses the stack
bottom-to-top. Callback changes are deferred safely, and screen timers are
cancelled when their owning screen exits.

Each screen registration has an explicit stack policy. Defaults implement a
paused transparent overlay: the underlay remains visible but does not update or
receive events. Opt in when an overlay should let selected work continue:

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

Events propagate top-to-bottom. Variable and fixed updates propagate
bottom-to-top, and state-local timers advance only for screens included in that
update pass. `draw_underlay=False` makes a pushed screen opaque and skips every
screen below it. `screens.policy(name)` returns an immutable `ScreenPolicy`;
`screens.get(name)` returns the one manager-owned instance. Registering one
class or object under multiple names and pushing one name twice are rejected.
`close()` exits the stack, cancels timers, releases instances, and is
idempotent.

Use it directly in the same Pygame loop as `World`:

```python
states = GameStates("playing")

@states.screen("playing")
class Playing:
    def event(self, event: object) -> None:
        if getattr(event, "type", None) == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            states.push("pause")

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass

@states.screen("pause")
class Pause:
    def event(self, event: object) -> None:
        if getattr(event, "type", None) == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            states.pop()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill((0, 0, 0, 120))

# In the loop:
for event in pygame.event.get():
    states.event(event)
    world.handle_event(event)
states.update(dt)
states.draw(overlay)
world.overlay.update(overlay)
world.update(dt)
world.render()
```

```python
from rix import EventBus, Subscription

events = EventBus(max_dispatch_depth=32)
token: Subscription = events.subscribe(
    "picked_up", lambda item: print(item), priority=10, once=False
)
events.emit("picked_up", "key")
print(events.listener_count("picked_up"))
events.unsubscribe(token)
events.clear()
```

```python
from rix import Easing, Tween

tween = Tween(
    0.0,
    1.0,
    0.5,
    easing=Easing.EASE_IN_OUT, # linear, ease_in, ease_out, ease_in_out
    loop=False,
    ping_pong=False,
    autostart=True,
    time_domain="render",
    on_update=lambda value: print(value),
    on_complete=lambda value: print("done", value),
)
value = tween.advance(dt, time_domain="render")
print(tween.value, tween.progress, tween.running, tween.finished)
```

`Tween` handles numbers, vectors, and equal-length tuples through normal arithmetic. Supply `interpolate(start, end, amount)` for custom types or a callable for custom easing. It also has `start`, `pause`, `resume`, `cancel`, `reset`, and wall-clock `poll`.

Standalone utilities remain manually advanceable. Optional registration uses
the existing game callbacks and prevents duplicate registration:

```python
game.manage_timer(timer)
game.manage_state_machine(machine)  # started, or constructed with an initial state
game.manage_tween(tween)
cube.animate("y", to=5, duration=1, easing="ease_in_out")
```

Entity-owned managed handles are cancelled when the entity is destroyed or
its scene is detached. `game.after` and `game.every` remain the shortest forms
for ordinary game-loop delays. Managed `Timer` and `Tween` objects retain their
own pause/resume behavior; pausing them makes scheduler advancement a no-op.
Game-level `after`/`every` callbacks use render/game-loop time, survive scene
replacement, and are cancelled when their handle is cancelled or the game is
closed. Callback exceptions follow the game's scheduler `fail_fast` policy.

## Optional multiplayer networking

Import networking explicitly with `from rix import net`. Messaging does not
construct a `Game`, SDL window, renderer, physics world, or scene, so it works
in ordinary Pygame programs and headless processes. The native backend is
GameNetworkingSockets when built with `RIX_ENABLE_NETWORKING=ON`.

### Beginner sessions and safe messages

`Session` is the smallest nonblocking message API:

```python
from rix import net

session = net.Session()

@session.on("chat")
def chat(sender: net.Player, *, text: str) -> None:
    print(sender.id, text)

session.host(port=7777)              # listen host + separate local client
# Or, in a separate process: session.join("127.0.0.1:7777")
session.send("chat", text="hello")  # this client identity -> authority
session.update(1 / 60)               # nonblocking event pump
session.close()
```

A host sends deliberately with `send_to(player, name, **fields)` or
`broadcast(name, **fields)`; server sends are never ambiguous. Pass
`unreliable=True` for replaceable data. `off(name, callback)` unregisters a
handler, and `disconnect(player, reason)` is host-only. `Session.players`
contains stable `net.Player(id, local, server)` values; `net.SERVER` represents
the authority in client callbacks.

Messages use bounded UTF-8 JSON with explicit byte tagging, never pickle or
code evaluation. Supported values are `None`, booleans, finite numbers,
strings, bytes-like values, lists/tuples, and dictionaries with string keys.
`net.encode_message()` and `net.decode_message()` expose the codec.

Optionally declare exact required fields with
`session.register_message("score", value=int, label=(str, type(None)))` and
remove a declaration with `unregister_message()`. Undeclared fields and exact
type mismatches are rejected; a peer that sends a malformed frame or violates
a registered receive schema is disconnected and `update()` raises
`NetworkError`.

A Pygame-only loop simply calls `session.update(dt)` beside the Pygame event
pump; RIX does not create or own a window in this mode. When the application
already has a RIX `World`, attach the session once and let `world.update(dt)`
pump it:

```python
session = net.Session()
session.join("127.0.0.1:7777")
world.attach_session(session)  # closes the session with the World by default

# Main loop: no separate session.update(dt) call.
world.update(dt)
```

Attached networking continues polling while world simulation is paused. Use
`world.detach_session(session, close=False)` to resume manual ownership, or
`close=True` to detach and close it. Pass `close_with_world=False` to
`attach_session()` only when the session deliberately outlives that world.

### Headless servers and transport

`net.Server(port=7777, max_players=32, tick_rate=60)` is a headless native
listener and fixed-step Python simulation owner. It supports `start()`,
`poll()`, one-tick `step()`, blocking `run()`, thread-safe `stop()`,
`send(connection, bytes)`, `broadcast(bytes)`, and `disconnect()`. Pass
`on_connect`, `on_disconnect`, and `on_message` callbacks to the constructor.
`load_scene(scene)` enables authoritative scripts and physics without a window
or GPU; `unload_scene()` detaches it.

`net.Client` provides `connect(host, port)`, `poll()`, `send()`,
`disconnect()`, state, statistics, and metrics. Both sides use `ConnectionId`,
`NetworkEvent`, `EventType`, `Delivery`, and `SendStatus`. Callbacks execute on
the thread calling `poll`, `step`, or `run`.

`net.ListenServer` combines one authority with an isolated local `Client`.
`start()` establishes the private host connection before returning; events are
tagged with `ListenRole` and `local_host`. It owns one authoritative simulation.

Direct numeric IPv4 and supported bracketed IPv6 addresses are accepted. This
does not provide arbitrary NAT traversal. A managed relay/room-code service and
generic rollback/lockstep are not currently implemented.

`SignalingServer` and `SignalingClient` provide an optional functional
self-hosted room directory. `generate_room_code()` creates a bounded readable
code; `RoomEndpoint.connection_string` supplies the numeric address to
`Session.join()`. Registration ownership follows the signaling connection and
is removed on disconnect. This directory does not relay game packets, discover
public endpoints, bypass NAT/firewalls, or constitute a managed hosted service.

### LAN discovery and deterministic impairment

`LanDiscoveryAnnouncer` publishes bounded compatibility metadata over UDP;
`LanDiscoveryBrowser` collects `DiscoveredServer` records without blocking.
Discovery is optional and does not replace the game transport.

For tests, `NetworkCondition` and `SimulatedLink` model bounded latency, jitter,
and loss. Presets are `LAN_NETWORK_CONDITION`,
`REGIONAL_NETWORK_CONDITION`, and `ADVERSE_NETWORK_CONDITION`.
`impair_backend(profile)` applies a process-global native test impairment and
rejects nested use.

### Typed replication, RPC, interest, and prediction

Replication is opt-in. Register local factories rather than accepting class
names from the wire:

```python
registry = net.PrefabRegistry(schema_version=1)
registry.register(1, "player", lambda scene: rix.Entity("player", scene=scene))
registry.register_variable(1, 1, "health", "int", 100, max_bytes=8)
registry.register_transform(1)

authority = net.ServerReplication(server, registry)
player = authority.spawn(1)
authority.set_owner(player.id, connection)
authority.variable(player.id, 1).value = 75
authority.flush()
authority.flush_transforms(server.tick_count)

mirror = net.ClientReplication(client, scene, registry)
mirror.poll()
```

`NetworkVar` supports bounded `bool`, `int`, `float`, `str`, `bytes`, `Vec3`,
and `Quat` schemas. Snapshot epochs, schema fingerprints, monotonic object IDs,
versioned deltas, explicit resynchronization, late joins, despawns, ownership
cleanup, transform history, acknowledged delta baselines, and full-baseline
recovery are implemented. `SpatialInterest` plus optional priority/bandwidth
budgets bounds transform fan-out.

Register RPC schemas with `PrefabRegistry.register_rpc(...)`; call client-to-
server methods with `ClientReplication.call_server()` and server-to-client or
broadcast methods with `ServerReplication.call_client()`/`broadcast_rpc()`.
RPCs validate direction, ownership, argument types and sizes, rate limits,
object lifetime, and delivery mode before invoking local handlers.

`PredictedCharacterController` sequences complete character inputs—including
jump, sprint, and crouch—on client and server. A server produces a
`CharacterCorrection`; a client restores authoritative native state and
replays only its bounded unacknowledged suffix. `RemoteTransformInterpolator`
applies buffered snapshots. This is character-motor prediction, not a generic
rollback engine.

`backend_info()` reports the compiled backend and version;
`backend_smoke_test()` performs a bounded native check. Transport, replication,
RPC, interpolation, and correction statistic records provide diagnostics.

### Authoritative match phases

Local menus, pause screens, and inventory remain ordinary `GameStates` and are
never networked implicitly. Shared match phase is an explicit registered
replication object:

```python
registry.register(20, "match", lambda scene: rix.Entity("match", scene=scene))
fields = net.register_match_state(registry, 20)

# Authority only:
spawned = authority.spawn(20)
match = net.ServerMatchState(authority, spawned.id, countdown_ticks=180)
match.start_match(server.tick_count)
match.advance(server.tick_count)  # call from authoritative simulation ticks

# Client after its replication snapshot is synchronized:
view = net.ClientMatchState(mirror, spawned.id)
print(view.phase, view.round, view.revision)
print(view.remaining_ticks(client_estimated_server_tick))
```

`MatchPhase` defines `WAITING`, `COUNTDOWN`, `PLAYING`, `ROUND_END`, and
`MATCH_END`. Only `ServerMatchState` can transition. `ClientMatchState` is a
read-only view; applying a replicated revision does not run server gameplay
callbacks on the client. Phase, round, monotonic revision, and optional
simulation-tick deadline are included in late-join snapshots.

## Debugging and diagnostics

Draw transient native debug geometry:

```python
from rix import debug

debug.line((0, 0, 0), (0, 2, 0), color="red", depth_test=True)
debug.axes(origin=(0, 0, 0), size=1.0)
game.scene.add_debug_line((0, 0, 0), (1, 1, 1), color="cyan")
game.scene.clear_debug_lines()
```

Inspect assets without starting a game:

```python
from rix import AssetKind, diagnose_asset

diagnostic = diagnose_asset("assets/model.glb")
print(
    diagnostic.kind, diagnostic.ok, diagnostic.summary, diagnostic.warnings,
    diagnostic.width, diagnostic.height, diagnostic.triangle_count,
    diagnostic.part_count, diagnostic.material_count,
    diagnostic.joint_count, diagnostic.clip_count,
    diagnostic.error_type, diagnostic.error_message,
)
```

`AssetKind` identifies image, OBJ, glTF/GLB, or unknown input. `AssetDiagnostic` is the immutable result.

Show live engine statistics with `DebugOverlay`:

```python
from rix import DebugOverlay

overlay = DebugOverlay(game, anchor="top_left", position=(12, 12), refresh_interval=0.25)
overlay.hide()
overlay.show()
overlay.update(0.25)
overlay.destroy()
```

## Errors, versioning, native smoke test, and typing

The public exception hierarchy includes `EngineError`, `AssetError`, `MissingAssetError`, `InvalidEntityError`, `PhysicsError`, and `ScriptCallbackError`. Catch the narrowest useful type:

```python
from rix import MissingAssetError, load_image

try:
    load_image("missing.png")
except MissingAssetError as error:
    print(error)
```

Read Python and native versions and test the extension boundary:

```python
import rix

print(rix.__version__)
print(rix.engine_version())
assert rix.native_add(2, 3) == 5
```

The package includes `py.typed` and a typed native stub (`_rix.pyi`), so editors, mypy, and Pyright can inspect the public Python and extension APIs.

Beginner-oriented submodules are `rix.input`, `rix.ui`,
`rix.physics`, `rix.audio`, `rix.time`, and `rix.scene`.
`rix.advanced` curates component facades, caches, diagnostics statistics,
constraints, and math types without removing their compatibility exports from
the root package.

## Included runnable examples

Run an example from the repository root with the installed interpreter:

```powershell
.\.venv\Scripts\python.exe examples\pygame\01_cube.py
```

Current example directories are:

- `examples/00_window`: minimal native window.
- `examples/01_entity_lifecycle`: entity creation and lifecycle.
- `examples/02_first_world`: basic rendered world.
- `examples/03_obstacle_course`: physics and character-controller course; also has `beginner.py`.
- `examples/09_hud`: retained native UI.
- `examples/10_audio`: audio loading and playback.
- `examples/11_gltf`: glTF model/metadata path.
- `examples/12_diagnostics`: diagnostics and debug overlay.
- `examples/13_autotexture`: automatic mapping/generation, advanced material
  maps, shared hot reload, and renderer texture telemetry.
- `examples/14_face_culling`: visual comparison of ordinary, front-cull, and
  two-sided normal-mapped rendering; choose a view with `--view`.
- `examples/15_lighting_sky`: multiple light kinds, bounded shadows, and
  procedural/panorama/cubemap sky rendering.
- `examples/beginner`: smaller beginner-facing programs.
- `examples/pygame/01_cube.py`: smallest Pygame-owned GPU window and RIX cube.
- `examples/pygame/02_game_loop.py`: Pygame polling moves a RIX entity.
- `examples/pygame/03_first_person.py`: forwarded input drives a native player.
- `examples/pygame/04_overlay.py`: Pygame font/drawing overlay in GPU mode.
- `examples/pygame/05_surface_texture.py`: one Pygame Surface used as a texture.
- `examples/pygame/06_dynamic_surface.py`: explicit per-change texture uploads.
- `examples/pygame/07_inventory_viewport.py`: inventory preview in Surface mode.
- `examples/pygame/08_billboards.py`: camera-facing Pygame images in 3D.
- `examples/pygame/09_menu.py`: a Pygame menu over a live 3D scene.
- `examples/pygame/10_physics.py`: fixed-step Jolt physics under Pygame timing.
- `examples/pygame/11_multiple_viewports.py`: independent cameras and Rect views.
- `examples/pygame/12_standalone.py`: retained RIX-only native-window path.
- `examples/pygame/13_migration.py`: `easy3d` to `rix` import migration.
- `examples/pygame/14_hybrid_minigame.py`: Pygame HUD/input with a RIX target.
- `examples/networking`: thirteen public examples covering authoritative
  Tic-Tac-Toe messages, Pygame chat/shared state, listen and dedicated servers,
  LAN discovery, direct IP, transform replication, cooperative 3D,
  authoritative FPS rules, health/scoring, character prediction/interpolation,
  and deterministic network impairment. See its `README.md` for the indexed
  commands and the real-versus-simulated distinction.
- `examples/06_two_process`: real independent-process low-level direct-IP
  transport example used by the process acceptance gate.
- `examples/states`: ten focused programs covering basic/conditional/timed
  states, lifecycle callbacks, screen changes, pause overlays, entity ownership,
  Pygame-only use, headless match state, and animation selection.

Use `.\.venv\Scripts\python.exe` consistently so the interpreter loading RIX
is the one containing pygame-ce 2.5.8 and the current editable native extension.

## Public symbol index

The root package currently exports the following supported names:

```text
ActionState, Anchor, AnimationChannelInfo, AnimationClipInfo, AnimationSelection, AssetDiagnostic,
AssetError, AssetKind, Audio, AudioSource, Billboard, Binding, Button, CallbackHandle,
CallbackStats, Camera, CharacterController, ClockDomain, Collider, CollisionEvent,
Column, Constraint, Cooldown, Cube, CullMode, DamageEvent, DebugOverlay, DeathEvent, Easing,
Enemy, EngineError, Entity, EventBus, Game, GameStates, GltfInfo, GraphicsPreset, Grid, HUD,
Health, HealthBar, HitscanWeapon, Image, ImageInfo, Input, Interaction,
InvalidEntityError, JointPose, Light, LightComponent, LightKind, Lighting, MeshRenderer,
MissingAssetError, Model, ModelCache, ModelInfo, ModelMaterialInfo, ModelPartInfo,
Panel, PhysicsError, PhysicsHit, PhysicsMaterial, Plane, Player, PointerState,
ProgressBar, Projection, Quat, RendererStats, Respawner, Rigidbody, Row, Scene,
Skybox, SkyboxKind,
SchedulerStats, Scoreboard, ScoreboardPanel, ScriptCallbackError, ShotResult,
SkeletonInfo, SkeletonJointInfo, Sound, SpawnPoint, Sphere, Sprite, Stack, State,
ScreenPolicy, ScreenTimer, StateMachine, Subscription, SurfaceTexture, Team, TeamRoster, Text, TextureCache, TextureFilter,
TextureMode, Timer,
Transition, Tween, UIElement, Vec2, Vec3, Viewport, World, __version__, debug, diagnose_asset,
engine_version, load_gltf, load_image, load_obj, native_add, net, physics
```

The optional `rix.net` package exports its session, transport, discovery,
replication, RPC, interpolation, prediction, and diagnostics types. They remain
namespaced instead of expanding the beginner root namespace.
