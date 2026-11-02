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
`MeshRenderer`, `Collider`, `Rigidbody`, and `CharacterController` are singleton native components and
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
sensor bodies.
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

### Queries

`easy3d.physics` exposes `raycast`/`raycast_all`,
`sphere_cast`/`sphere_cast_all`, `capsule_cast`/`capsule_cast_all`,
`overlap_sphere`, and oriented `overlap_box`. Directions are normalized by the
engine and `max_distance` supplies the cast length. Capsule `height` is total
tip-to-tip height and must exceed its diameter; its local axis is +Y before the
optional public rotation.

All results are immutable `PhysicsHit` snapshots containing a generation-safe
entity wrapper, world-space point/normal, distance and normalized cast fraction.
Ray/shape-cast results are sorted nearest first with entity ID as a stable tie
break. Overlaps are deduplicated and sorted by entity ID. `layers` is an
explicit subset of `static`, `dynamic`, `sensor`, and `character`;
`include_triggers=False` rejects sensors, and `exclude=entity` rejects exactly
that scene-local generation. Invalid/cross-scene exclusions and non-finite or
degenerate geometry raise instead of producing partial results.

### Contact and trigger events

Scripts may implement `on_collision_enter`, `on_collision_stay`,
`on_collision_exit`, `on_trigger_enter`, `on_trigger_stay`, and
`on_trigger_exit`. Each receives a frozen `CollisionEvent(other, point,
normal)`. The normal points from the recipient toward `other`; the second
recipient gets the inverse normal. Exit uses the last safe contact snapshot.

Jolt's contact listener copies bounded native records only. After
`PhysicsSystem::Update` and dynamic pose synchronization, the scheduler drains
those records and invokes Python on the gameplay thread under the existing
profiling/fail-fast/quarantine policy, then commits deferred destruction. A
contact event is offered to both live, enabled, started script entities.
Destroying an entity/body drops events that cannot provide two valid entity
handles rather than exposing a stale reference. The current simple shapes have
one subshape; compound-shape contact aggregation remains with Phase 2.8.
Jolt may retire solver contacts when all moving bodies sleep; Easy3D retains
the logical pair without emitting a false exit, reports stay if it is detected
again, and emits exit when an awake/separated or destroyed pair is reconciled.

### Character controller

`Player(controller="first_person" | "third_person")` is the convenience form
of `Entity + CharacterController`. The controller is a native, bottom-aligned
Y-axis capsule. Public `height` is total tip-to-tip height in meters. Its
construction-time configuration includes `radius`, `height`, `speed`,
`acceleration`, `air_control` in `[0,1]`, `jump_speed`,
`max_slope_degrees` in `[0,90)`, and `step_height`.

`set_input((right, 0, forward), heading_degrees=..., jump=...)` stores one
fixed-tick command. Input magnitude is clamped to one. At heading zero,
positive forward moves along world -Z; heading rotates movement around +Y.
First-person mode makes the entity face the supplied heading. Third-person
mode faces nonzero movement while still interpreting it relative to heading.
Jump is a one-shot request consumed by the next native step; movement and
heading persist until replaced. `grounded`, `ground_normal`, and
`linear_velocity` are solver snapshots.

The native fixed phase updates each character velocity and calls Jolt
`CharacterVirtual::ExtendedUpdate` before `PhysicsSystem::Update`. This gives
the motor slope cancellation, stair walking, floor adhesion, collision/sliding,
moving-ground velocity, gravity, and jump behavior on the simulation thread.
A smaller Jolt inner capsule makes characters visible to ordinary queries,
rigid bodies, sensors, and deferred contact events on the `character` layer.
Character transforms are physics-owned, cannot be parented, and must use
`teleport(position, heading_degrees=...)` for discontinuities. A character
controller and ordinary collider are mutually exclusive on one entity.

`CharacterInputCommand(sequence, movement, heading_degrees=0, jump=False)` is
an immutable validated input value. `PredictedCharacterController(controller,
role="client" | "server", max_pending_inputs=256)` drives the same native motor
on both sides. Client `submit(...)` allocates a strictly increasing uint64
sequence, applies immediately, and appends to `pending_inputs`; a full queue or
sequence exhaustion raises `NetworkError`. Server `accept(command)` has no
replay queue and native code rejects zero, duplicate, or stale sequences before
input changes.

After stepping accepted input, authority `make_correction(server_tick)` returns
an immutable `CharacterCorrection` containing a nondecreasing acknowledged
sequence, strictly newer uint64 simulation tick, position, normalized rotation
and velocity. Client `reconcile(correction, fixed_delta_seconds=...)` rejects a
future/backward acknowledgement or stale tick, restores the authority state,
removes the acknowledged prefix and replays every retained newer input through
the ordinary native motor without advancing the whole scene. The queue bound is
therefore also the replay-work bound. `CorrectionStats` reports correction,
replay and pre-snap position-error totals/max/average. Direct offline
`CharacterController.set_input` remains unsequenced; `correct_state` and
`replay_input` expose the lower-level mechanics. Easy3D does not serialize these
values automatically; games choose their bounded input/correction channel.

`RemoteTransformInterpolator(client_replication, delay_ticks=2)` applies the
existing clamped remote transform histories at authority tick minus delay.
Authority ticks cannot move backward. `RemoteInterpolationStats` exposes calls,
applied objects and the last authority/render ticks. It does not extrapolate or
operate on the local predicted character.

Every `Scene` creates its physics world lazily. `scene.gravity` reads the default
`(0, -9.81, 0)` without allocation and creates the world when changed. During a
simulation tick the scheduler runs all eligible Python `fixed_update(dt)` hooks,
commits deferred mutations, then advances the initialized Jolt world once with
that same fixed `dt`, synchronizes dynamic poses and dispatches copied contact
events. `scene.physics_step_count` is a diagnostic. Scene clear
destroys all native bodies and characters and invalidates their handles. A scene with no
physics use pays no Jolt-world/temp-buffer allocation.

### Advanced shapes, constraints, and CCD

`Collider` supports `box`, `sphere`, `capsule`, `convex`, and `mesh`. Capsule
height is total tip-to-tip height and must exceed its diameter. Convex hulls
accept 4–256 finite `points` or the vertices of an OBJ `mesh` asset. Triangle
meshes are built from triangulated OBJ parts, use counter-clockwise one-sided
triangles, and are static-only; attaching a `Rigidbody` is rejected. `Model`
accepts `collider="mesh"` or `collider="convex"`. Model scale is baked into an
advanced collider when it is created and later scale changes do not rebuild it.

`Rigidbody(continuous=True)` selects Jolt linear-cast motion quality for dynamic
bodies. It addresses high-speed linear tunneling but does not promise perfect
collision for long, thin bodies with extreme angular velocity. Static and
kinematic bodies reject the option.

`easy3d.physics.fixed_constraint(first, second)` welds two collider bodies at
their current relative pose. `distance_constraint` accepts optional world-space
anchors and either automatic initial length or a validated
`minimum_distance`/`maximum_distance` range. The returned `Constraint` is
generation checked, exposes `is_alive`, and has explicit `remove()`. Endpoints
must be distinct entities in one scene and at least one body must move.
Destroying/replacing either endpoint body removes its constraints before the
body. Phase 2.8 intentionally provides fixed and distance joints first; hinge,
slider, motorized and compound-shape APIs remain future extensions.

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

## Network transport foundation

`easy3d.network.NetworkTransport` is a runtime-checkable Python protocol for a
polled endpoint. `send(bytes_like, delivery=...)` returns `SendStatus` instead
of blocking or silently growing a queue. `poll(maximum_events)` returns immutable
`NetworkEvent` snapshots; `stats` is an immutable counter snapshot. A
`ConnectionId` is opaque local transport state and is never an entity or future
replication ID.

`SimulatedLink` owns `first` and `second` endpoints. `latency`, `jitter`, and
manual `advance()` values are seconds; `loss` is in `[0, 1]`. The seed and
explicit queue/message limits make impairment tests reproducible. Construction
enqueues one connected event per endpoint. Disconnecting either side enqueues a
disconnected event for both and invalidates further sends.

The simulator preserves `Delivery.RELIABLE`/`UNRELIABLE` as intent only. It
models datagram impairment and does not retransmit. Event queue exhaustion raises
`NetworkError` once and leaves already-queued events available to a subsequent
poll. No socket, server, client, handshake, or replication API is claimed by
this foundation.

`NetworkCondition(name, one_way_latency_seconds, jitter_seconds,
loss_probability)` validates GNS-compatible bounds. The exported LAN, regional
and adverse profiles are `(5ms, 2ms, 0%)`, `(40ms, 10ms, 1%)`, and `(100ms,
30ms, 5%)`; `REPRESENTATIVE_NETWORK_CONDITIONS` preserves that order.
`profile.create_simulated_link(seed=...)` uses the deterministic packet-level
semantics above.

`impair_backend(profile)` returns a context manager for real GNS testing. A
`Server` or `Client` must already keep GNS initialized before entry. The scope
applies send-side lag/jitter/loss process-wide, rejects nested/concurrent scopes,
and clears every setting on normal or exceptional exit. GNS reliable delivery
continues to retransmit/order; unreliable delivery may be lost. This is a test
facility, not per-connection QoS, and the named profiles are regression inputs
rather than network-quality promises.

`backend_info()` returns a frozen `NetworkBackendInfo` containing availability,
backend name/version and configured crypto provider. On the supported Windows
build it reports GameNetworkingSockets 1.6.1 with Windows BCrypt.
`backend_smoke_test()` temporarily owns the process-global native runtime and
performs a bounded reliable loopback round trip. It is a build/runtime
diagnostic, not a public client connection or network security test.

The native `easy3d::detail::ProtocolHandshake` is an internal contract for the
future `Client` and `Server` owners, not a Python gameplay API. It must be
started once, consumes one complete reliable transport message at a time, and
returns an optional outbound reply plus establishment/rejection state. It
negotiates a maximum application payload no larger than either peer's declared
limit. Peer bytes never raise parsing exceptions; malformed, incompatible,
out-of-order or oversized input returns a stable disconnect code and bounded
safe-text reason. Addresses, timeout clocks and socket ownership remain outside
this codec.

## Direct-IP client

`easy3d.network.Client(...)` accepts finite positive `timeout` and
`peer_timeout` values, bounded queue/message/version values, and optional
`on_connect(client)` and
`on_disconnect(client, event)` callables. `connect(address, port)` accepts a
numeric IPv4/IPv6 address and port `1..65535`, starts asynchronously, and rejects
an already-active client. DNS names are not accepted. `state` is one of
`disconnected`, `connecting`, `handshaking`, or `connected`; `connection` is an
opaque `ConnectionId` while active and `None` after close.

`poll(maximum_events=256)` must be called by one owning thread. It advances the
transport and handshake, enforces the deadline, returns immutable events, and
then dispatches Python callbacks in event order on that same thread. Callback
exceptions propagate to the caller after the native event has been drained.
They are never invoked on a GNS callback or worker thread.

`send(bytes_like, delivery=...)` returns `SendStatus`; it does not block or
raise for normal inactive/oversize/backpressure outcomes. `disconnect(reason)`
requires an active connection. Reason text is at most 120 UTF-8 bytes with no
control/NUL characters. `stats` contains application counters. `metrics` adds
state, GNS ping/recent rates/pending bytes and the negotiated payload limit;
unavailable live values retain documented zero/`-1` defaults.

`timeout` covers initial transport connection and protocol handshake.
`peer_timeout` configures GNS connected-peer liveness detection and defaults to
10 seconds; it is finite and in `[0.001, 2147483.647]`. Disconnect observation
still requires polling and backend scheduling, so the configured value is not
an exact wall-clock callback deadline.

## Headless authoritative server

`easy3d.network.Server(...)` (also exported as `easy3d.Server`) accepts a
numeric `bind_address`, port `1..65535`, `max_players` in `1..1024`, positive
`tick_rate`/handshake/peer timeouts and bounded queue/message/protocol settings. It is
headless by construction: no graphics option is necessary and no window,
renderer or input owner is created. `start()` binds without entering the
simulation loop. `state`, normalized `bind_address`, active `port`, immutable
`connections`, counters and `tick_count` are observational snapshots.

`load_scene(scene)` gives the server exclusive scene ownership. `run()` blocks
on its calling thread, services networking, and executes authoritative Python
lifecycle plus native physics at the configured fixed rate until `stop()` is
requested. `stop()` may be called from another Python thread. `step()` starts
the listener if necessary and executes exactly one network pump/fixed tick;
`poll()` services networking without advancing simulation. Scenes can be
replaced only while `run()` is inactive.

`send(connection, bytes_like, delivery=...)`, `broadcast(...)` and
`disconnect(...)` operate only on post-handshake opaque IDs. Optional
`on_connect(server, connection)`, `on_message(server, event)` and
`on_disconnect(server, event)` callbacks execute synchronously in event order
on the `run`/`step`/`poll` caller. Callback exceptions propagate after the event
is drained and are not replayed. The dedicated `Server` itself implies no local
client, player identity, entity replication, DNS or discovery behavior.

The server's `peer_timeout` configures the same GNS connected-peer liveness
policy for accepted clients. `ListenServer` passes one value to its isolated
authority and local client. Abrupt backend/OS failure codes are retained as
integers when they are outside Easy3D's stable application-code range.

## Isolated listen host

`easy3d.network.ListenServer(...)` (also `easy3d.ListenServer`) composes one
authoritative `Server` with one real loopback `Client`. `start()` binds and
completes the private host handshake before returning. Its returned
`ListenEvent` values and optional `on_event(host, event)` callback tag every
event with `ListenRole.AUTHORITY` or `ListenRole.CLIENT`; `local_host` is true
for the private host peer and false for additional remote peers.

`authority` and `client` remain separate typed objects. Only `authority` may
own the scene, scheduler, physics and Python lifecycle. `authority_connection`
is the authority-side opaque ID for the private client. It can have the same
numeric value as `client.connection`, but equality across those two role-local
spaces has no identity or ownership meaning. Use the role tag and the object
that produced the ID.

`step()` pumps both transports and executes exactly one authority tick.
`run()` reuses the server's paced owner loop and pumps the client after each
authority tick; it never executes the scene a second time. `stop()` is a
thread-safe request while running and closes both roles when manually stepped.
`poll()` services both transports without simulation. Additional direct-IP
clients appear only as authority events with `local_host=False`. The local host
receives no implicit privilege, player identity, entity replication, rendering
or prediction behavior.

## Opt-in LAN discovery

`easy3d.discovery.LanDiscoveryAnnouncer(name, game_port, ...)` and
`LanDiscoveryBrowser(...)` (also exported at package root) are explicitly
started, single-owner IPv4 UDP objects. They are independent of `Server` and
`Client`; callers must poll the announcer alongside a running authority and
must explicitly choose a `DiscoveredServer.address`/`port` for a later
`Client.connect()` call. Neither object owns a thread or changes Windows
Firewall configuration.

The announcer name is non-empty, control-free UTF-8 capped at 128 bytes. Ports,
protocol/schema versions and optional persistent 64-bit instance ID are
validated before a socket opens. `poll(maximum_packets)` accepts only complete
format-1 query datagrams, caps work at its configured per-poll limit, rate
limits repeat source addresses and bounds rate-limit state. `start()` reports
bind/port-collision failures as `NetworkError`; `close()` is idempotent.

The browser binds an ephemeral UDP port only after `start()`. `refresh()` sends
one random nonzero nonce to the configured limited/directed broadcast address
and replaces the prior response window. `poll()` ignores malformed and stale/
unmatched responses, accepts responses only from the configured discovery
port, and returns newly validated immutable `DiscoveredServer` values. Its
`servers` property is the current finite-capacity, finite-TTL cache. A result's
`compatible` flag is exact protocol/schema comparison; incompatible results
remain visible but are not connected automatically. Stats are immutable
snapshots. Discovery supplies no DNS, IPv6 broadcast, authentication, account
identity, room directory, relay or cross-subnet guarantee.

## Server-owned replicated lifecycle

`PrefabRegistry(schema_version=..., capacity=...)` maps explicit nonzero 32-bit
`PrefabId` values and unique 1–64-byte safe UTF-8 names to
`factory(scene) -> Entity` callables. Its 16-byte fingerprint is computed from
the schema version and canonical ID/name pairs, independent of registration
order. Attaching a replicator freezes the non-empty registry. IDs/names cannot
be duplicated and capacity is finite.

`ServerReplication(server, registry, max_objects=...)` must attach before
clients connect and preserves the server's existing callbacks. `spawn(prefab)`
requires an authority scene, invokes its factory, assigns a monotonic nonzero
64-bit `NetworkObjectId`, and reliably broadcasts the lifecycle. IDs are never
derived from `Entity.id` and are not reused after despawn. `despawn(id)` sends
the authoritative removal and destroys the mapped authority entity. Failed
replication queueing disconnects that peer so a reconnect can rebuild from a
fresh snapshot instead of silently diverging.

On each post-handshake connection the authority sends snapshot begin, current
spawns sorted by object ID, and matching end. The begin declares bounded count,
registry schema and fingerprint. `ClientReplication(client, scene, registry)`
consumes only `E3DR` lifecycle messages, validates exact framing/order/count and
creates/destroys client entities. `poll()` returns non-replication network
events; callers must not also poll the same client independently. Disconnect
clears replicas. Client-authored `E3DR` messages are rejected by the authority.

Lifecycle is the reliable base for the Phase 4 replication contract. Prediction
is a separate typed character-input surface and is not automatically attached
to replication transport.

`PrefabRegistry.register_variable(prefab, field_id, name, type, default,
max_bytes=...)` adds a canonical field definition before freeze. Supported
types are `bool`, signed `int`, finite `float`, control-free UTF-8 `string` and
copied `bytes`; values must fit the declared bound. `ServerReplication.variable`
returns a writable authority `NetworkVar`. Actual changes increment its uint64
version and mark it dirty; equal assignments do not. `flush()` reliably queues
dirty fields and clears their dirty flags. Client variables are read-only and
accept only known object/field/type updates with strictly newer versions.
Late-join snapshots include every current field value before snapshot end.

`PrefabRegistry.register_transform(prefab)` adds a `NetworkTransform` schema
marker and changes the registry fingerprint. `ServerReplication.flush_transforms`
accepts a nondecreasing uint64 simulation tick, assigns a monotonic uint64
sequence and queues one fixed position/quaternion/scale frame per relevant
object/connection using unreliable delivery. Local-space values must be finite;
quaternions are normalized and scale components must be nonzero. Per-flush work
is capped by `max_transform_sends`. `TransformFlushStats` reports queued,
filtered, backpressured, budget-deferred, full/delta and byte counts;
replaceable backpressure does not disconnect an otherwise healthy peer.

`ServerReplication` defaults to a per-connection transform token budget of 256
KiB/s, 64 KiB burst and 60 simulation ticks/s. All are bounded constructor
arguments. An optional `priority(connection, object)` returns a finite numeric
priority. `SpatialInterest(radius)` stores explicit connection observer
positions, filters objects outside the radius and contributes nearer-first
priority; object ID is the stable final tie-breaker. These policies never
suppress reliable lifecycle, variables or RPCs.

Each accepted full/delta sample is ACKed reliably. Authority sends a 64-byte
quantized delta only from that connection/object's ACKed snapshot; otherwise it
sends the 76-byte full frame. Delta ranges are signed int16 centimeters for
position, 1/16000 quaternion-component difference and 1/1000 scale difference.
Overflow/invalid reconstruction falls back to full. Sent baseline candidates
and client histories are bounded. If a delta names an evicted client baseline,
the client drops it and sends a monotonic reliable recovery request; authority
clears that one baseline and its next relevant update is full.

`ClientReplication(..., max_transform_samples=32)` stores at most 2–256 samples
per object. Unknown, duplicate, stale-sequence and older-tick unreliable frames
are dropped and counted rather than treated as connection corruption; malformed
or schema-incompatible frames remain fatal. A newer sample for the same tick
replaces that tick. `transform_snapshots(id)` exposes the immutable sample
sequence and `interpolate_transforms(render_tick)` clamps outside history,
linearly interpolates position and same-sign scale, steps mirrored scale sign
changes to avoid an invalid zero scale, and normalized-shortest-path
interpolates rotation before applying only to client replica entities. The
optional server
`relevance_filter(connection, object)` suppresses transform frames only; it does
not despawn the object or hide its lifecycle/NetworkVar state.
`delta_baseline_stats` exposes full/delta receive, ACK and recovery-request
counts.

`PrefabRegistry.register_rpc(prefab, rpc_id, name, direction, arguments,
handler, reliable=..., rate_limit=..., require_owner=...)` adds a stable RPC to
the frozen fingerprint. `arguments` is a tuple of `(NetworkValueType,
max_bytes)` pairs with at most 16 entries. Supported values are the exact
bounded primitive `NetworkVar` codecs. Client-to-server handlers receive
`(authority_entity, sender_connection, *arguments)`; server-to-client handlers
receive `(client_entity, *arguments)`. Handler lookup is registry-only.

After initial synchronization, `ClientReplication.call_server` validates the
local direction/schema and queues the declared delivery. The authority requires
a known live object, newer per-connection invocation sequence, matching
direction, and—when configured—`ServerReplication.owner(id) == sender`. It then
enforces the registered per-second sliding limit before calling the handler on
the server poll thread. `set_owner` accepts established connections only and
clears ownership on disconnect. Excess calls are counted and dropped;
malformed, replayed, wrong-direction or ownership-tampered calls disconnect the
sender.

`ServerReplication.call_client` and `broadcast_rpc` perform the inverse schema
check and clients reject malformed, replayed or client-to-server calls from the
authority channel. `RpcStats` reports received/executed/rate-limited counts.
Reliable delivery does not confer authority. Game-specific validation remains
the registered handler's responsibility.

## Replicated match state

`register_match_state(registry, prefab)` adds four bounded int64 fields to a
dedicated prefab: phase, round, deadline simulation tick and transition
revision. `ServerMatchState` accepts only `ServerReplication`, validates
nondecreasing signed-int64 ticks and implements legal transitions among
`WAITING`, `COUNTDOWN`, `PLAYING`, `ROUND_END` and `MATCH_END`. Countdown and
intermission expiry is advanced explicitly from the authority simulation tick;
wall-clock/render time never changes match authority.

`ClientMatchState` accepts only `ClientReplication` and provides read-only
properties plus `remaining_ticks(current_tick)`. All four values use the normal
reliable dirty-field stream and complete late-join snapshot. A listen host has
one `ServerMatchState` on its authority; its local transport client has no
second timer or authority transition path.

## Replication resynchronization

`ClientReplication.request_resync()` is available only after initial sync and
queues a reliable nonzero monotonic request. The authority validates replay and
a 250 ms minimum interval, removes that peer from live-update recipients, and
queues the same complete epoch/schema/lifecycle/value/transform snapshot used
for late join. Readiness returns only after snapshot end is queued. Snapshot
begin clears and recreates client replicas; exact same-version/same-value field
updates crossing the boundary are idempotent, while older or conflicting
versions remain protocol errors.
