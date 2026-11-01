# Easy3D implemented API contract

## Scene and entity lifecycle

```python
from easy3d import Entity, Game, Scene

scene = Scene("main")
with scene:
    player = Entity("player")
    prop = Entity("prop")

game = Game("Example")
game.load_scene(scene)

assert player.is_alive
player.enabled = False
prop.destroy()

game.unload_scene()
scene.close()
```

Outside a `with scene:` block, pass `scene=...` or call
`scene.create_entity()`. Easy3D deliberately raises an actionable `RuntimeError`
instead of selecting an unqualified global world.

`Entity.destroy()` invalidates every wrapper to that entity. `Scene.clear()`
invalidates all current entities but leaves the scene reusable. `Scene.close()`
clears and permanently closes it. Access through a stale wrapper raises
`InvalidEntityError`, which is a Python `ReferenceError` subclass:

```python
from easy3d import InvalidEntityError

entity = scene.create_entity()
entity.destroy()

try:
    print(entity.name)
except InvalidEntityError:
    pass
```

Implemented entity properties include `id`, `name`, `enabled`, `visible`,
`scene`, `is_alive`, local/world transforms, `parent`, and `children`.
`MeshRenderer`, `Collider`, and `Rigidbody` are singleton native components and
are available through typed `has_component`, `get_component`, and
`remove_component`; physics components are attached with `add_component`.
Network identity remains a later checklist item.

## Renderable entities and components

```python
from easy3d import Cube, MeshRenderer, Model, Plane, Scene, Sphere

world = Scene("world")
with world:
    floor = Plane(size=(20, 20), color=(0.3, 0.35, 0.4))
    cube = Cube(position=(0, 0.5, 0), texture="assets/crate.png")
    ball = Sphere(position=(2, 0.5, 0), radius=0.5)
    prop = Model("assets/prop.obj", position=(-2, 0, 0))

renderer = cube.get_component(MeshRenderer)
assert renderer is not None
renderer.color = (0.8, 0.9, 1.0)
renderer.lit = False
```

`Cube`, `Plane`, `Sphere`, and `Model` are normal subclassable `Entity` values
that transactionally attach one native `MeshRenderer`. Construction failures
destroy the partially created entity. Primitive mesh allocations and parsed OBJ
assets are shared across instances; the private renderer also shares GPU buffers
by immutable resource identity. A primitive texture is decoded/cached at
construction. OBJ parts apply their MTL diffuse color and optional diffuse map.

Primitive dimensions are expressed through entity scale: cube `size` accepts a
positive scalar or XYZ tuple, plane `size` a scalar or width/depth tuple, and
sphere `radius` a positive scalar. `MeshRenderer.color` is multiplicative RGBA
with finite components in `[0,1]`; `kind` and `asset` are read-only, and
`lit` selects baseline ambient/directional lighting versus unlit vertex/material
color, and `remove()` detaches the component.

The loaded scene is traversed natively for every rendered frame. No per-entity
Python draw calls occur. The renderer reads the scene-owned camera, native light
components, and render components during that traversal. Public scene/entity/
component mutation is allowed during scheduler hooks on the gameplay thread;
other threads raise `RuntimeError` while `Game.run()` is active.

## Math and transform conventions

`Vec2` and `Vec3` provide finite components, arithmetic, dot products,
normalization, and explicit approximate comparison. `Vec3` also provides cross
products. `Quat` is stored as `(w, x, y, z)` and supports normalization,
multiplication, vector rotation, and degree-based Euler conversion.

Entity `position`, `rotation`, and `scale` are local-space live properties:
`entity.position.x += 1` writes through to native state. `world_position`,
`world_rotation`, `world_quaternion`, and `world_scale` are calculated snapshots.
The coordinate system is right-handed, +Y up, with camera-forward -Z. Euler
angles are degrees and are not unique: reading a rotation may produce a different
but orientation-equivalent triple. Compare quaternions when orientation identity
matters.

`entity.set_parent(parent, keep_world=False)` preserves the local transform by
default. Pass `keep_world=True` to recompute local TRS while preserving the
current world transform. Parenting rejects self-parenting, cycles, stale handles,
and cross-scene relationships. Destroying a parent detaches its direct children
while preserving their world transforms.

## Camera configuration

```python
from easy3d import Camera

camera = Camera(
    position=(0, 3, 8),
    vertical_fov_degrees=60,
    near_plane=0.1,
    far_plane=500.0,
)
camera.look_at((0, 0, 0))
scene.camera = camera
view = camera.view_matrix()
projection = camera.projection_matrix((1280, 720))
```

`Camera` is right-handed with local forward -Z and uses degree-based public
Euler rotation backed by native quaternion math. FOV must be strictly between
0° and 180°; near must be positive; far must exceed near. Projection matrices
are column-major. D3D-style projection maps depth to `[0,1]`; the explicit
`homogeneous_depth=True` query maps it to `[-1,1]` for backend testing.

Set `projection="orthographic"` and a positive `orthographic_height` to select
an orthographic volume. The height remains fixed while the renderer derives its
width from the current pixel aspect ratio, so resize behavior matches the
perspective camera's undistorted vertical framing.

`Camera.aspect_ratio((width, height))` and `projection_matrix` reject zero or
non-integer dimensions. The renderer uses current SDL pixel dimensions after
every resize. Assigning `scene.camera` copies the current camera value into the
native scene. Reading `scene.camera` returns a detached typed copy; change it and
assign it back when updating several fields. Cameras are scene values rather
than entity components in this baseline.

## Lighting, materials, and debug lines

```python
from easy3d import Cube, Light, Scene, debug

scene = Scene("lit world")
with scene:
    Light("ambient", color=(0.5, 0.6, 1.0), intensity=0.2)
    sun = Light("directional", intensity=0.9, rotation=(-35, -30, 0))
    lit_cube = Cube(position=(-1, 0, 0), color=(0.9, 0.2, 0.1))
    unlit_cube = Cube(position=(1, 0, 0), color=(0.2, 0.9, 0.3), lit=False)
    debug.axes(size=2.0)
    debug.line((-2, 0, 0), (2, 0, 0), depth_test=False)
```

`Light` owns one native `LightComponent`. Ambient light colors are multiplied by
intensity and accumulated. The first enabled directional light supplies its
world-space local -Z direction and color/intensity; additional directional
lights are retained as components but not blended by this baseline. If a scene
has no explicit light of a kind, the renderer keeps its corresponding usable
default ambient or directional contribution. Disabled light entities are
ignored. Light color components are finite in `[0,1]`; intensity is finite and
non-negative.

Baseline lit materials apply diffuse Lambert lighting to both solid and
textured RGB while retaining material alpha. Normals use the inverse-transpose
world transform, so non-uniformly scaled objects remain correct. There are no
shadows, specular/PBR channels, transparent sorting, or gamma-adjustable light
units yet. Pass `lit=False` during primitive/model construction or set
`MeshRenderer.lit` before running the game for unlit color.

`debug.line` and `debug.axes` append persistent native scene lines. Depth-tested
and overlay lines are batched separately into frame-local transient GPU buffers.
They persist until `scene.clear_debug_lines()` or `scene.clear()`; debug drawing
does not create entities and does not cross into Python once per rendered frame.

## Renderer visibility and counters

```python
game.run()
print(game.renderer_stats)
# RendererStats(draw_calls=..., visible_instances=..., culled_instances=...,
#               instanced_draw_calls=...)
```

Before submission, the renderer tests a conservative transformed bounding sphere
derived from each mesh's cached local AABB against the current scene-camera
frustum. `visible_instances` and `culled_instances` count mesh parts, so a
multi-part OBJ may contribute more than one. Disabled, invisible, and
non-renderable entities contribute neither. `draw_calls` counts submitted 3D
and debug batches; `instanced_draw_calls` is the subset using instance data.

Visible items with identical mesh, material state/color, and texture/sampler are
grouped. Two or more compatible items with uniform absolute XYZ scale use one or
more bgfx instance buffers; non-uniformly scaled items fall back to individual
draws to preserve exact inverse-transpose normals. `Game.renderer_stats` returns
a coherent, immutable `RendererStats` snapshot from the latest completed frame
and is safe to sample from a monitoring thread while `Game.run()` has released
the GIL.

## Input and remappable actions

Each `Game` owns one `game.input` object. Physical control identifiers are
lower-case `device:name` strings: `key:w`, `mouse:left`,
`mouse:delta_x`, `mouse:wheel_y`, `gamepad:a`, and `gamepad:left_x` are
representative values. Keyboard identifiers describe physical SDL scancodes,
so `key:w` means the physical W position rather than layout-produced text.

`Input.bind(name, *bindings, replace=True)` atomically replaces an action map;
pass `replace=False` to append. A string creates a unit digital binding.
`Binding(control, scale=..., deadzone=...)` supports opposing directions,
axis inversion, and one-dimensional deadzones. Contributions sum and clamp to
`[-1, 1]`; deadzone magnitude is rescaled to retain the full post-deadzone
range. `state()` returns an immutable value/down/pressed/released snapshot.
Unknown actions raise `IndexError` rather than silently returning an
unconfigured value.

Mouse position is window-relative; delta and wheel accumulate for the current
frame and reset at the next native event poll. The current baseline opens one
primary SDL gamepad and uses Xbox-style logical face names `a/b/x/y`; axes are
normalized to `[-1,1]`, while triggers use `[0,1]`.

Setting `pointer_lock_requested` asks the window thread to enter SDL relative
mouse mode. `pointer_locked` reports the applied state. Losing keyboard focus
clears all held controls, produces action releases at the next frame boundary,
and disables the applied lock without discarding the request. Gaining focus
reapplies it. The input object is mutex-protected for monitoring threads; Phase
2.2 will make action reads deterministic inside gameplay callbacks.

## Script lifecycle and scheduler

An `Entity` subclass is registered as a script when it defines any of `awake`,
`start`, `fixed_update`, `update`, `late_update`, or `on_destroy`. `awake` runs
once when the scheduler first sees the entity. `start` runs once when that
entity is first enabled; disabling and re-enabling does not repeat it. Disabled
entities receive no fixed/render updates. `on_destroy` runs once before native
handle invalidation, including scene clear.

Input events are drained before the native frame callback. The scheduler then
runs zero or more `fixed_update(fixed_dt)` calls, followed by one `update(dt)`
phase and one `late_update(dt)` phase before renderer submission. The default
fixed rate is 60 Hz. Frame delta clamps to 0.25 seconds and catch-up is capped at
five ticks; excess whole-tick time is dropped and reported rather than causing
an unbounded spiral. Configure these with `Game(fixed_hz=...,
max_frame_seconds=..., max_catch_up_steps=...)`.

Entity destruction and `Scene.clear()` requested inside a hook are deferred to
the end of that callback phase. Other transform/component/camera mutations are
safe immediately because callbacks execute on the SDL/render-owning thread
before traversal. Uncontrolled worker-thread mutation remains rejected.

The default `fail_fast=True` wraps callback failures in `ScriptCallbackError`
with hook, entity type/name, and generation-qualified ID while preserving the
original exception as its cause. The native loop unwinds and resets running
state. With `fail_fast=False`, the traceback is printed, the failing entity is
quarantined from later hooks, and the summary appears in `game.script_errors`.
`game.scheduler_stats` exposes fixed tick/drop/overrun totals and immutable
per-hook call/total/maximum/last durations.

## Standalone gameplay utilities

`StateMachine` registers named `State` objects, validates event transition
endpoints up front, calls `on_exit(target)` before `on_enter(source)`, resets
`time_in_state` on transition, and evaluates guarded transitions in registration
order. Direct `transition_to` is available for unconditional control. Public
machine operations from inside enter/update/exit/guard callbacks raise a
reentrancy error rather than nesting a partial transition. Callback exceptions
propagate to the caller; if an enter callback fails, the target remains current
so state is never reported as the already-exited source.

`Timer`, `Cooldown`, and `Tween` each declare a `ClockDomain`: `simulation`,
`render`, or `wall`. Simulation/render objects advance only through
`advance(dt, time_domain=...)`; passing the wrong explicit domain raises.
Wall-clock objects use `poll()` and accept an injectable monotonic clock for
tests. Negative/non-finite deltas are rejected. Timers support pause/resume,
one-shot/repeat completion counts and a bounded repeat-callback burst.
Cooldown activation is rejected until ready unless `restart=True`. Tween
supports scalar/vector arithmetic, equal-sized tuples, custom interpolators,
linear/ease-in/ease-out/ease-in-out curves, looping and ping-pong.

`EventBus` dispatches synchronously by descending priority and then subscription
order. One-shot listeners are removed before invocation, so recursive emission
cannot call them twice. Unsubscribing a listener before its turn suppresses it;
new listeners wait for the next emission. Nested dispatch is supported up to a
configurable bound. Listener exceptions propagate without being hidden.

## Physics components and foundation

```python
from easy3d import Collider, Entity, PhysicsMaterial, Rigidbody, Scene

world = Scene("physics")
floor = Entity("floor", scene=world)
floor.position = (0, -0.5, 0)
floor.add_component(
    Collider,
    half_extents=(5, 0.5, 5),
    material=PhysicsMaterial(friction=0.8, restitution=0.0),
)

ball = Entity("ball", scene=world)
ball.position = (0, 3, 0)
ball.add_component(Collider, shape="sphere", radius=0.5)
body = ball.add_component(Rigidbody, mass=2.0)
body.add_impulse((2, 0, 0))
```

Jolt Physics is private behind `easy3d::PhysicsWorld`; no Jolt type crosses the
public engine boundary. `PhysicsBodyHandle` contains physics-world identity,
slot and generation, so stale and cross-world access raises `PhysicsError`.
World configuration bounds bodies, broadphase pairs, contact constraints and
temporary allocation. Capacity update errors are surfaced rather than ignored.

The baseline object layers are `Static`, `Dynamic`, `Sensor`, and `Character`.
Static/static and sensor/sensor pairs do not collide; other baseline pairs do.
Static objects use Jolt's non-moving broadphase; all other layers use the moving
broadphase. Public box/sphere `Collider` values use explicit meter dimensions;
`Cube`, `Plane`, and `Sphere` can create matching colliders with
`collider=True`. A collider without a `Rigidbody` is static. Attaching a
`Rigidbody` selects dynamic or kinematic motion. Trigger colliders use Jolt
sensor bodies; collision/trigger event snapshots remain Phase 2.6.
Collider geometry is captured in world-meter dimensions at construction and is
not implicitly resized by later entity-scale changes; remove/recreate the
collider when changing shape dimensions.

`PhysicsMaterial` validates non-negative friction and restitution in `[0,1]`.
Rigid-body mass is positive kilograms, linear velocity is meters/second, force
is newtons, and impulse is newton-seconds. `use_gravity=False` gives the body a
zero gravity factor without changing its scene. Forces and impulses require a
dynamic body. Component construction is transactional, entity destruction
releases its body, removing a rigid body returns its collider to static motion,
and removing a collider also removes rigid-body motion.

Dynamic transforms are physics-owned and synchronized to entities after every
native step. Direct entity transform writes are rejected while a dynamic body
is attached; `Rigidbody.teleport(position, rotation)` is the explicit override.
Static and kinematic transform writes update Jolt immediately. Physics entities
cannot be parented in this release because local/world conversion under moving
parents is not yet a defined solver contract.

Every `Scene` creates its physics world lazily. `scene.gravity` reads the default
`(0, -9.81, 0)` without allocation and creates the world when changed. During a
simulation tick the scheduler runs all eligible Python `fixed_update(dt)` hooks,
commits deferred mutations, then advances the initialized Jolt world once with
that same fixed `dt`. `scene.physics_step_count` is a diagnostic. Scene clear
destroys all native bodies and invalidates their handles. A scene with no
physics use pays no Jolt-world/temp-buffer allocation.

## Texture assets

```python
from easy3d.assets import TextureCache, load_image

info = load_image("assets/albedo.jpg", color_space="srgb")
cache = TextureCache()
shared = cache.load("assets/albedo.jpg")
assert len(cache) == 1
```

`load_image` accepts `.png`, `.jpg`, and `.jpeg`, decodes to four-channel
RGBA8 storage, and returns immutable metadata. `TextureCache` owns shared native
image resources and uses a deterministic canonical-path plus color-space key;
`clear()` drops cache ownership without invalidating already referenced native
resources. Cache access is thread-safe. It is intentionally synchronous until
the later asynchronous asset milestone.

Color textures default to `srgb`; data textures can request `linear`. Public
mesh UV `(0, 0)` refers to the first/top-left decoded texel, `u` increases right,
and `v` increases down. Native `TextureSampler` supports linear/nearest min,
mag, and mip choices plus repeat/clamp U/V modes. The current D3D11 diagnostic
visibly validates nearest sampling and repeat defaults. GPU cache identity
includes both the immutable decoded image and sampler settings.

A missing/non-file path raises `MissingAssetError`, an `AssetError` subclass.
Malformed files and unsupported extensions raise `AssetError` with the path and
decoder context. The public API never exposes bgfx handles.

Graphics-disabled/headless builds retain the asset types and deterministic error
surface but deliberately do not link image decoders; attempting image decode in
that configuration raises `AssetError`. Dedicated servers do not need texture
pixels. A future headless content-validation tool may split decoding into a
separate optional build feature if that becomes a concrete requirement.

## OBJ model assets

```python
from easy3d.assets import ModelCache, load_obj

model = load_obj("assets/house.obj")
cache = ModelCache()
shared = cache.load("assets/house.obj")
```

The OBJ importer preserves positions, normalized supplied normals, texture
coordinates, and optional per-vertex RGB. Faces are triangulated. If any corner
of a triangle lacks a normal, Easy3D creates a flat geometric normal and unique
vertices for that triangle. Degenerate triangles are rejected. OBJ V is flipped
(`v_engine = 1 - v_obj`) into Easy3D's top-left texture convention; U is
unchanged. Shapes are split again by material so every `ModelPartInfo` has one
material index.

`ModelCache` is thread-safe, holds immutable native model/mesh data, and uses a
canonical path key. `Model` entities reference that shared data rather than
parsing or copying the model again.
Clearing the cache does not invalidate outstanding native shared references.
OBJ loading and caching work in graphics-disabled/headless builds.

Supported MTL fields are material name, diffuse `Kd`, dissolve `d`/`Tr`, and
diffuse texture `map_Kd`. Diffuse texture paths are currently resolved relative
to the OBJ directory; keep MTL files and their referenced textures under that
root. Missing MTL files, unknown material names, missing diffuse textures,
invalid indices, empty geometry, and malformed files are errors. Other MTL
channels/options (specular/normal maps, illumination models, PBR extensions,
multiple texture layers) are parsed by the dependency where possible but not
represented or claimed by Easy3D. Smoothing-group normal generation is not yet
implemented: provide normals for smooth shading, otherwise output is flat.
