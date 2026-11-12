# RIX implemented API contract

This document describes the supported public Python surface. Names beginning
with `_` and the C++ implementation are private unless documented otherwise.

## Package and errors

`rix.engine_version()` returns the native version. `rix.__version__`
comes from the same `VERSION` file. `EngineError`, `AssetError`,
`MissingAssetError`, `InvalidEntityError`, and `PhysicsError` are the public
native exception hierarchy.

Optional multiplayer APIs live under `rix.net`; the root exports the `net`
module but does not flatten transport and replication types into the beginner
namespace. `rix.net.NetworkError` is the networking exception. Builds with
`RIX_ENABLE_NETWORKING=OFF` retain importable APIs but report an unavailable
native backend rather than silently simulating internet connectivity.

`rix` and `rix._rix` are authoritative. The transitional `easy3d` package
emits `DeprecationWarning` and aliases the same classes, submodules, and native
extension; mixed imports cannot create a second renderer runtime.

## Pygame-owned World

`World(screen, mode="gpu", fixed_hz=60, max_frame_seconds=0.25,
max_catch_up_steps=5, ...)` requires the active Pygame CE display Surface on
Windows. Pygame owns the window, queue, input polling, main loop, frame clock,
and default audio. `handle_event(event)` translates only the supplied event and
returns whether it was recognized. It never calls `pygame.event.get()`.

`update(dt)` accepts finite non-negative seconds and advances the same scheduler,
bounded fixed physics, callbacks, characters, collision delivery, timers, and
deferred lifecycle operations as standalone Game. It never sleeps or advances
physics a second time. `pause()` freezes simulation while rendering remains
available.

In GPU mode, `render()` lets bgfx/D3D11 perform the only presentation; calling
Pygame display flip/update is unsupported. `set_overlay(surface)` installs a
full-display, alpha-blended Pygame Surface copied into a native texture after
3D/post-processing. Later changes require `world.overlay.update(surface)`.

In Surface mode, `render()` renders offscreen, performs synchronous GPU
readback, and returns an owned RGBA Pygame Surface without presenting. Pygame
then owns the blit and `display.flip()`. `world.to_surface()` repeats blocking
readback of the latest full-window 3D frame.

`close()` is idempotent and must run before `pygame.quit()` so bgfx releases its
swap chain before Pygame destroys the HWND. One bgfx renderer session may be
active in the process.

`SurfaceTexture(surface, srgb=True)` copies pixels, alpha, and row layout into
owned contiguous RGBA8 storage. `.update(surface)` is explicit and revisioned;
RIX never borrows Surface memory or automatically uploads each frame.
`Viewport(world, size=... | rect=..., camera=...)` owns a copy of the supplied
camera (or a snapshot of `world.camera`) and renders the shared scene into a
dedicated native target of exactly that size. Its first default `to_surface()`
blocks to produce an immediate image. Later default refreshes queue a native
readback and return the newest completed cached Surface, normally one frame
behind without stalling presentation. `blocking=True` waits for fresh pixels;
`blocking=False` may return a transparent placeholder before the first request
completes. `close()` cancels/abandons safely and is idempotent. Multiple
Viewports have independent cameras, sizes, and cached output but share the
world simulation and renderer thread. They do not claim input focus or consume
events: the Pygame application decides which preview is active (typically with
`viewport.rect.collidepoint(event.pos)`) and mutates that Viewport's camera.
`Billboard(world, image=..., axis="free"
| "y")` is a double-sided textured quad that faces the active camera.

## Game

`Game(title="RIX", resolution=(1280, 720), vsync=True, fps_limit=0, ...)`
owns the native engine/window and optionally constructs a default scene,
camera, lighting, and audio context. `run()` blocks until the native window
closes or `stop()` is requested. `running` and `tick(fps=None)` provide a
Pygame-style manual loop over the same native frame step and scheduler.
`close()` is idempotent, closes a dormant manual session, and rejects closing
inside an active frame or blocking managed loop.

Each native frame calculates elapsed time, pumps SDL events, finalizes input,
invokes the Python scheduler callback, runs bounded fixed simulation and
gameplay callbacks, updates the audio listener, renders/presents exactly once,
publishes counters, and applies the selected limit. Code after manual `tick()`
is visible on the next presented frame. Managed and manual control cannot be
mixed or entered recursively.

Callbacks registered through `on_update`, `on_fixed_update`, input shortcuts,
and timers run on the gameplay thread. Handles returned by registration can be
cancelled. Callback mutation is permitted only inside the scheduler's guarded
boundary.

## Scene and entity lifetime

`Scene` owns a native world ID and generational entity handles. Entity handles
cannot cross scenes; destroyed handles raise `InvalidEntityError`. `Entity`
provides name, active state, local/world transforms, parent/children,
components, lookup, duplication helpers, and explicit `destroy()`.

Every entity slot owns zero-initialized `velocity`, `acceleration`,
`angular_velocity`, and `angular_acceleration`. All are live assignable vectors;
linear values use world units and angular values use degrees. Ordinary entities
integrate them on the fixed clock using semi-implicit Euler, including through
parent transforms. `speed`, `movement_direction`, `forward`, `right`, `up`,
direction conversion, `face_direction()`, and `launch()` provide typed helpers.
Facing remains opt-in.

`teleport(..., reset_motion=False)` preserves motion by default. Disabling an
entity snapshots and freezes its motion while physics collision remains
stationary; re-enabling restores it. Slot destruction/reuse clears motion.

The active `with scene:` context controls convenience construction. A `Game`
may attach one active scene; load/unload operations keep ownership explicit.

## Rendering

`Cube`, `Sphere`, `Plane`, and `Model` are convenience entities built over
`MeshRenderer`. Material controls include color, texture, opacity, roughness,
metallic response, emissive color, and shadow flags. Camera projection,
lighting, debug lines, visibility, culling, instancing, renderer counters,
quality presets, shadows, and post-processing are native.

`Cube`, `Sphere`, `Plane`, and `Model` accept
`cull_mode: Literal["back", "front", "none"] | None` and
`double_sided: bool | None`. Omitting both selects back-face culling for
primitives. `double_sided=True` is shorthand for `cull_mode="none"`, while
`False` selects `"back"`; incompatible simultaneous values raise `ValueError`
instead of silently choosing one. `Entity` and `MeshRenderer` expose live,
synchronized `cull_mode` and `double_sided` properties.

For imported models the precedence is explicit constructor/runtime override,
then glTF material `doubleSided`, then back-face culling. OBJ has no equivalent
flag and therefore uses the fallback. An explicit model override applies to all
parts. Culling state participates in the instancing compatibility key and is
also applied to shadow submission. Negative-determinant transforms swap front
and back culling so the semantic visible side is preserved. Two-sided lit and
normal-mapped fragments reverse the final shading normal for back faces;
unlit shading remains unaffected.

Face culling discards triangles by winding. It is independent of depth testing
and does not mutate geometry, colliders, physics contacts, or raycast results.

The current graphics backend is Windows D3D11 through bgfx. Python never owns
an OpenGL or Direct3D context.

## Input and player

`Input` exposes remappable actions plus immutable per-frame keyboard, mouse,
pointer, and gamepad state. `Player` composes a native `CharacterController`
with first-/third-person camera policy. Default controls support move, look,
jump, sprint, crouch, pointer capture, and release. `controls=False` disables
automatic polling for code-driven movement.

`Player` character tuning uses `move_speed` and `move_acceleration`. The old
scalar `speed` and `acceleration` constructor calls fail with migration
guidance. `view_forward`, `view_right`, and `view_up` include camera look;
inherited facing vectors describe the character body.

Physical `key`, `mouse`, press, and release helpers coexist with named action
maps. `Game.on_key` and `Game.on_mouse` are edge decorators. `Game.raycast`,
`Entity.raycast`, and camera-aware `Player.raycast` delegate to the existing
physics query path and return `PhysicsHit`.

Action edges preserve a press and release that both arrive in one native poll.
`Game.on_input`, `Game.on_key`, and `Game.on_mouse` dispatch those edges during
the variable-rate update of the same rendered frame rather than waiting for a
fixed tick. This prevents quick interactions from being lost on high-refresh
frames that perform no physics step.
The automatic `Player` samples jump during render update and latches it until
one fixed step consumes the request, so a faster render clock cannot lose a
jump between physics ticks. Jump is edge-triggered and is neither buffered nor
resubmitted while held. Normalized movement input uses ground friction and
projection-based acceleration. Airborne movement has no friction and caps only
the wish-direction projection, so forward-only input cannot continually gain
speed while a perpendicular strafe can curve and increase total speed. A jump
pressed on a grounded landing tick skips friction and preserves momentum.

`CharacterController.set_sequenced_input()` accepts strictly increasing,
nonzero input sequences and includes movement, heading, jump, sprint, and
crouch intent. `last_input_sequence`, `correct_state()`, and `replay_input()`
are the native boundary used by `rix.net.PredictedCharacterController` for
bounded client reconciliation. Ordinary `set_input()` remains valid and does
not advance the network sequence.

## Optional networking

`rix.net.Session` is a nonblocking safe-message façade for RIX, Pygame-only,
and headless programs. `host()` creates one listen authority plus an isolated
local logical client; `join()` creates only a client. `send()` routes from the
session's client identity to its authority. Server routing is explicit through
`send_to()` or `broadcast()`. Named handlers are added with `on()` and removed
with `off()`. User callbacks run only from `update()`.

The application codec is bounded UTF-8 JSON supporting only documented basic
values and explicitly tagged bytes. It rejects non-finite numbers, non-string
mapping keys, excessive nesting/containers, malformed frames, and oversized
payloads. It does not deserialize classes, use pickle, or evaluate code.

`rix.net.Client`, `Server`, and `ListenServer` expose the lower typed transport.
`Server` owns a fixed-step scheduler and optional authoritative `Scene`, and
can run without a window, renderer, Pygame, or GPU. `Client.connect()` and
`Session.join()` do not create an implicit authority. Reliable and unreliable
delivery, bounded native queues, timeouts, protocol/schema handshake,
backpressure status, metrics, clean disconnect, and gameplay-thread callback
dispatch are part of the transport contract.

`PrefabRegistry` declares local prefab factories, typed `NetworkVar` fields,
transforms, and bounded RPC schemas. `ServerReplication` owns monotonic object
IDs, authoritative values, ownership, snapshots/deltas, transform baselines,
interest and budget policy, and RPC validation. `ClientReplication` mirrors
registered objects, requests explicit resynchronization, interpolates bounded
transform history, and dispatches allowed RPCs. Neither side imports arbitrary
classes named by remote input.

`PredictedCharacterController` is a character-motor-specific sequencing and
reconciliation helper. It is not a generic deterministic rollback system.
`LanDiscoveryAnnouncer`/`LanDiscoveryBrowser` provide optional IPv4 LAN
advertisement. `SignalingServer`/`SignalingClient` provide a bounded optional
self-hosted room-code directory whose result is a numeric direct endpoint.
Direct IP and room lookup do not promise NAT traversal; hosted matchmaking and
packet relay infrastructure are outside the implemented contract.

`World.attach_session(session)` makes the existing Pygame/RIX frame update the
sole poll point for that session. Attached sessions continue polling while
simulation is paused and close before the World by default. Detachment restores
manual polling. Calling `Session.update()` manually while it is attached is an
application error because it would create two event-dispatch points.

Replicated match phase is opt-in and separate from local UI state.
`register_match_state()` declares stable phase/round/deadline/revision fields;
`ServerMatchState` is the only transition owner and advances from monotonic
server ticks. `ClientMatchState` exposes a read-only late-join-safe view and
never executes authority callbacks merely because a revision arrived.

## State and animation selection

`StateMachine(initial)` supports decorator and advanced registration APIs,
safe deferred `change()`, stable prioritized conditions, state-local timers,
and bounded transition loops. Initial entry occurs on the first update so all
decorators are installed first. `Entity.state_machine(initial)` registers the
machine exactly once with its owning `Game` and ties cancellation to entity
lifetime.

`AnimationSelection.play(name, restart=False)` tracks current/previous clip
intent and a revision counter without restarting the same name by default.
State `animation=` metadata drives an attached entity's selection. This does
not extend the renderer contract to GPU skeletal deformation; imported models
still render their base pose.

## Physics

`Collider`, `Rigidbody`, `CharacterController`, `PhysicsMaterial`, and
`Constraint` expose Jolt through RIX-owned handles. Supported behavior
includes static/dynamic/kinematic bodies, trigger events, contact snapshots,
raycasts, shape casts, overlaps, box/sphere/capsule/mesh shapes, fixed/distance
constraints, CCD, impulses, forces, teleport, slopes, steps, sprinting,
crouching, ground friction, air strafing, and edge-triggered jumping.

Physics stepping occurs on the fixed clock. Native results are immutable
snapshots when delivered to Python.

## Optional multiplayer contract

`rix.net` exposes transport, Session messaging, registered replication/RPC,
supported character prediction, LAN discovery, match state, and the optional
self-hosted signaling directory. Signaling only resolves a room code to a
numeric direct endpoint. No public API promises a packet relay, NAT traversal,
hosted matchmaking, generic lockstep, or generic rollback.

The future rollback boundary is normative in `docs/rollback-contract.md` but
is not currently importable. In particular, `PredictedCharacterController`
does not make an Entity, Scene, Python callback, or Jolt world deterministic.

Dynamic/kinematic bodies expose their actual linear velocity and degree-based
angular velocity through both `Entity` and `Rigidbody`. Entity acceleration is
added independently of mass and gravity. Character linear velocity is
assignable; character angular motion is Y-only to preserve upright collision.
Adding/removing physics ownership transfers current motion. Collider-only
static entities reject nonzero motion and direct callers to a kinematic body.

## Assets

`load_image`, `load_obj`, `load_gltf`, and `load_fbx` validate bounded local
filesystem assets. `TextureCache` and `ModelCache` reuse immutable native data.
OBJ/MTL, PNG/JPEG, glTF/GLB, and binary/ASCII FBX use shared immutable model,
material, skeleton, and animation records.

`Model.add_animation(name, path)` attaches a compatible FBX/glTF/GLB clip.
`Model.play(name, *, loop=True, speed=1, blend=0, root_motion=False,
on_complete=None)` restarts it and advances automatically. Pause/resume/stop,
clip/time/duration/speed/state, and `animation_skinning` are public and typed.
Completion callbacks run once on Python's normal late-update boundary. Every
instance owns its controller; cache entries remain shared.

Skeleton compatibility requires same-named target joints, named-parent
agreement, and bounded rest scale/length/orientation. Four influences are
retained. D3D11 GPU palettes support 64 joints and larger rigs use bounded
native CPU transient skinning. A model part is deformed once per frame and its
compact transient buffers are reused across main and shadow passes. In-place playback is default. Root motion is
explicit: the owner receives horizontal X/Z translation and root yaw, while
vertical root translation and pitch/roll remain in the animated pose and do not
accumulate onto the owner across loops. Root motion cannot take ownership from
dynamic bodies, character controllers, or collider-only static objects.

### AutoTexture and material maps

`Game` accepts optional `pixels_per_unit=16`, `texture_filter="nearest"`,
`texture_mode="auto"`, and `texture_hot_reload=True` defaults. `Cube`, `Plane`,
and `Sphere` accept per-object versions plus `normal_map`, `roughness_map`,
`metallic_map`, `emissive_map`, `ambient_occlusion_map`, and
`normal_strength=1.0`, plus optional `roughness`, `metallic`, and `emission`
scalar factors. A missing local `.png` base path is generated
automatically; an existing malformed file raises `AssetError` and is not
replaced.

Automatic mapping selects tile for cubes/planes, spherical for spheres, and
preserve for imported authored UVs. `texture_mode="atlas"` selects the
documented cube cross. `normal_map=False` disables discovery. Otherwise the
engine searches conventional suffixes. `MeshRenderer` exposes live primitive
texture/map/density/filter/mode/normal-strength properties without replacing
the entity. Map-backed roughness/metallic/emission defaults use a neutral scalar
factor of one; absent maps retain the legacy `0.5`/`0`/`0` scalar defaults.
Atlas face regions retain their creation-time world proportions when local or
parent scale changes; live world dimensions continue to drive tile/sphere
mapping.

`TextureCache.load(..., hot_reload=True)` shares canonical path/color-space
entries and `poll_changes()` returns the number of valid replacements. A failed
reload retains the prior image. `RendererStats` additionally reports
`cpu_frame_ms`, `gpu_frame_ms`, `texture_count`, and
`texture_memory_bytes`; zero timing means the active backend did not report that
counter.

## Advanced lighting and skyboxes

`Light.type` accepts `"ambient"`, `"directional"`, `"point"`, and `"spot"`.
All lights expose `color` and non-negative `intensity`; local lights expose a
positive `range`, and spots expose full-cone `angle` plus `inner_angle` where
`0 <= inner_angle <= angle < 180`. `casts_shadows`, `shadow_resolution` (zero
means preset default), and `shadow_bias` are live. Entity transforms determine
position/direction and `enabled=False` removes a source from selection.

Multiple sources coexist. The first explicit ambient or directional light
removes the matching beginner defaults, while later explicit sources supplement
it. The automatic scene uses low ambient plus a warm key/cool fill directional
rig so axis-aligned faces do not collapse to one ambient shade. The fill tracks
the `game.lighting.directional` key intensity at its default ratio.
`Scene.lights(kind=None)` returns live registered lights. Preset budgets are
`1/4/2`, `2/16/8`, `4/32/16`, and `4/64/32` for directional/point/spot.

Every `Scene` starts with a procedural `Skybox`; `Game.skybox` proxies the
active scene. Assignment accepts a `Skybox`, a panorama path, `"default"`, or
`None`. A panorama must be exactly 2:1. Cubemap folders/mappings use
right/left/top/bottom/back/front square images of identical size. Missing paths
generate bounded PNG templates with exclusive writes.

`RendererStats` adds active counts per light kind, `culled_lights`,
`shadow_passes`, `active_shadow_casters`, `dropped_shadow_casters`, and
`shadow_memory_bytes`.

## Audio

`Audio`, `Sound`, and `AudioSource` provide bounded WAV loading, playback,
mixing, looping, volume, pitch, and positional attenuation. SDL owns the output
device; RIX owns decoded PCM and voice state.

## UI

`HUD`, `Panel`, `Text`, `Image`, `Sprite`, `Button`, `ProgressBar`,
`HealthBar`, `ScoreboardPanel`, and row/column/grid/stack containers form a
retained native overlay. Layout, anchors, visibility, hit testing, and button
callbacks remain bound to the owning game and scene.

## Gameplay utilities

Public convenience helpers include health/damage/death, enemies, hitscan
weapons, interactions, spawn/respawn, teams, scoreboards, event buses, timers,
cooldowns, state machines, easing, and tweens. They compose normal entities,
physics queries, callbacks, and UI rather than a parallel runtime.

`Entity.add_health`, `Player.add_weapon`, `Game.manage_timer`,
`Game.manage_state_machine`, `Game.manage_tween`, and `Entity.animate` add
optional managed ownership while preserving standalone/manual advancement.
Managed entity helpers cancel on entity destruction or scene detachment and
must never be registered twice. `Game.play_sound` uses the existing per-game
WAV cache and playback backend.

Managed `Timer` and `Tween` registrations preserve the utility's selected
clock domain and pause/resume state. Game-level `after` and `every` use
render/game-loop time, persist across scene replacement, and end on explicit
cancellation or game close. Scheduler exception handling remains governed by
the game's `fail_fast` setting.

Curated `rix.time` and `rix.advanced` modules improve discovery without
removing compatible root exports.

## Diagnostics and typing

Asset diagnostics, the debug overlay, renderer/scheduler counters, `.pyi`
stubs, `py.typed`, and strict consumer type checks are part of the supported
developer experience. Diagnostics observe state and do not mutate scenes.
