# RIX architecture

## Display adapters

The Scene, scheduler, Jolt world, renderer traversal, and GPU resource managers
are shared by three adapters:

- standalone managed/manual `Game` owns an SDL3 window, SDL3 events, bgfx
  presentation, optional native audio, and timing;
- Pygame GPU `World` validates Pygame's Win32 HWND and gives bgfx sole
  presentation ownership while Pygame owns the loop and event queue;
- Pygame Surface `World` renders to the existing HDR framebuffer, post-processes
  into an RGBA8 target, blits to a bgfx readback texture, waits for completion,
  and returns copied pixels without presenting.

Independent `Viewport` rendering selects a camera copy and exact target size,
temporarily binds a cached HDR/depth framebuffer, post-processes to a cached
RGBA8 target, and reads into a request-owned staging texture and pixel buffer.
The first default request waits for a usable image. Later requests are polled
after ordinary bgfx frames and update the Python Surface cache only when ready;
abandoned requests retain their storage until bgfx's completion frame, avoiding
dangling write pointers and premature GPU resource destruction.

Pygame CE's SDL2 and RIX's private static SDL3 never pump or destroy the same
window. The external session talks to the validated HWND directly and does not
initialize SDL3 video/audio. Both Pygame modes advance the existing Python
`SimulationScheduler`; there is no second physics engine or timing loop.

Pygame Surface uploads convert through `pygame.image.tobytes(..., "RGBA")` into
owned `ImageData`. Render components hold shared ownership. A monotonically
increasing revision causes the existing GPU texture cache to replace the bgfx
handle on the next render. Full-window overlays reuse the native retained UI
pass after post-processing.

## Ownership model

`Game` owns a native engine, window, renderer, input state, audio output, and
one active scene attachment. `Scene` owns one native world, entity storage,
render components, physics resources, camera data, and UI/debug state. Python
wrappers hold world-scoped generational handles rather than native pointers.

Destruction flows from owners to children. Teardown is idempotent and occurs on
the gameplay/window thread so SDL, bgfx, Jolt, and Python callbacks never race
an uncoordinated worker.

## Native/Python boundary

C++ owns hot loops and retained data. Python owns game rules, composition, and
callbacks. The pybind11 boundary uses RIX value types, tuples, strings,
bytes, and handles; third-party types never enter the public API. Native
exceptions translate to the typed Python hierarchy.

## Frame and simulation flow

One persistent native window session implements both blocking `Game.run()` and
one-frame `Game.tick()`. Each frame follows this order:

1. Calculate steady-clock elapsed time.
2. Poll SDL events and publish physical/action input edges.
3. Invoke the Python scheduler callback on the gameplay/window thread.
4. Run bounded fixed steps, local character input, Jolt, and contact snapshots.
5. Run variable and late callbacks and commit deferred mutations safely.
6. Update the audio listener and submit native scene/UI rendering.
7. Present exactly once, publish counters, and apply FPS limiting.

Manual-loop mutations after `tick()` occur between native frames and become
visible on the next presentation. They are allowed only on the owning gameplay
thread. Managed callbacks can mutate at their existing guarded boundary.

The standalone `Game` frame has no implicit networking stage. A Pygame `World`
may explicitly own attached `Session` objects; `World.update(dt)` polls each
once before input finalization and simulation, including while paused.
Pygame-only and headless programs poll their networking objects directly.

## Rendering

The scene retains mesh/material/light/camera data independent of bgfx. The
Windows renderer maps it to D3D11 resources, performs conservative culling and
compatibility-key instancing, submits optional shadow/post-process passes, and
draws the retained overlay. Resource caches use stable RIX keys and release
GPU objects before renderer shutdown.

Cull mode is retained as material state rather than a mesh mutation. Standard
CCW RIX fronts map to bgfx's D3D11 `CULL_CW` for back-face culling;
front-face culling uses `CULL_CCW`, and two-sided rendering sets no cull flag.
The renderer swaps front/back state for negative-determinant world transforms,
includes cull mode in compatibility batching, and carries the same effective
state into shadow batches. Imported-model resolution is explicit component
override, glTF material `doubleSided`, then back culling. Consequently one
model can preserve authored per-part culling until the caller requests a
whole-model override.

The lit fragment paths use `gl_FrontFacing` to reverse the completed surface
normal on back fragments. This occurs after tangent-space normal-map
reconstruction, so tangent handedness and mapped detail remain coherent while
the unlit path stays color-only. Depth testing and physics retain separate
state and are not affected by culling.

AutoTexture preparation is deliberately split across the boundary. Python
chooses automatic mapping, safely creates missing editable PNG/JSON files, and
resolves conventional companion names. C++ owns decoded RGBA8 images, cache
identity, tangents, world-scale mapping uniforms, mip generation, GPU lifetime,
and shader sampling. Runtime scale changes therefore update mapping uniforms
without regenerating a texture. Tile and sphere modes read the live composed
world scale. Atlas mode instead retains the positive world dimensions used to
generate/attach its fixed PNG cross, preventing later nonuniform or parent scale
changes from shifting normalized face rectangles.

Each `RenderComponent` retains albedo, normal, roughness, metallic, emissive,
and AO images plus sampler/density/mapping settings. Albedo and emissive images
use sRGB GPU flags; data maps remain linear. The fragment shader combines map
samples with scalar material factors and receives a tangent basis generated for
primitive and imported meshes. The vertex shader applies the model determinant
sign when reconstructing bitangents, while nonuniform transforms use the
inverse-transpose path instead of instancing. Texture cache revisions trigger a
safe GPU handle replacement at frame submission; invalid saves retain the last
valid decoded image. Renderer entries hold weak image ownership and are
collected after a safe frame; clearing the final scene owner also clears its CPU
texture and model caches.

## Physics

Each scene lazily constructs one Jolt world. Bodies, characters, and constraints
use separate RIX handles. Fixed stepping is native. Transform precedence is
explicit: simulated bodies publish state to entities; teleports and kinematic
targets are explicit commands. Contact listeners enqueue snapshots rather than
calling Python from Jolt internals.

Every world slot also contains reset-on-reuse motion state. The scene fixed
step applies semi-implicit linear integration and world-axis quaternion deltas
to ordinary entities, converting the resulting world transform back to local
space for parented objects. Physics-owned entities delegate velocity to Jolt;
RIX applies universal acceleration before each solver step and synchronizes
the resulting state afterward. Character yaw is accumulated separately from
camera look so angular motion does not discard mouse/gamepad aiming.

Disabling snapshots transform and velocity, holds the physics proxy stationary
but collidable, and restores the snapshot on enable. Attaching/removing a body
or character transfers motion rather than silently resetting it.

## Input, audio, assets, and UI

SDL owns device event delivery and audio-device callbacks. RIX retains
action maps and a bounded PCM mixer. Asset loaders convert third-party parser
output into immutable RIX data. UI layout and hit testing use native retained
state while Python owns callback policy.

## Convenience layer

Default scenes, primitive entities, `Player`, gameplay helpers, and UI widgets
compose the same native systems as explicit construction. Context-local defaults
avoid one process-wide hidden world. Every convenience has an explicit-scene or
component-level escape hatch.

## Shared model animation pipeline

OBJ, glTF/GLB, and FBX import into immutable `ModelData` cache entries. ufbx is
private parser infrastructure: its axes, units, pivots, layered curves, and
clusters are converted at import time into the same `MeshData`, `Skeleton`,
`AnimationClip`, and material structures used by glTF. Render components hold
only per-instance controller/pose state and a shared model pointer.

The fixed scene step samples local TRS channels, applies optional pose blending,
builds hierarchical globals, and handles in-place or explicit owner root
motion. The renderer combines globals with inverse binds. Rigs at or below 64
joints upload 3 matrix rows per joint to D3D11 vertex shaders; larger rigs are
deformed once per model part per frame into compact, bounded native transient
buffers reused by visible and shadow passes. The configured pools are 32 MiB
for vertices and 8 MiB for 32-bit indices. Python never loops over vertices or
joints for ordinary playback.

## Bounded lighting and sky rendering

Lights remain entity components in the native scene. Each frame the renderer
sums ambient sources, frustum-culls point influence volumes and rotated spot
cone bounds, then performs a stable shadow-first/relevance/id ordering into
fixed D3D11 uniform arrays. All fragment material paths consume the same
direct-light implementation.

Shadow selection is bounded to one directional, one spot, and one point source
in high/ultra. Directional and spot sources use R32F depth-value targets; point
sources render radial depth into six R32F cubemap faces. Per-light
bias/resolution is validated before target recreation, and telemetry exposes
selection loss, passes, and allocated bytes.

The scene owns an optional sky definition and decoded images. A fullscreen
direction reconstruction draws before geometry in the main sequential view,
ignoring camera translation while using camera rotation. Procedural,
equirectangular, and cubemap skies therefore share the geometry
post-process/FXAA target. Replaced image and cubemap resources are retired.

## Optional networking layers

`rix.net` separates the native GameNetworkingSockets transport, Python
session/message routing, and registered game-state synchronization. Transport
callbacks enqueue bounded events; Python handlers execute only when the
application calls `poll()` or `Session.update()`. Message-only clients and
headless servers do not construct SDL, bgfx, a window, or a scene. Replication,
RPC, prediction, and discovery remain opt-in layers over the same transport.

`RIX_ENABLE_NETWORKING=OFF` retains a bounded stub backend. The initial real
backend is Windows/MSVC direct IP with BCrypt. The optional self-hosted
signaling directory resolves bounded room codes to numeric direct endpoints but
does not relay traffic or traverse NAT. Generic deterministic rollback is not
part of the verified implementation; `docs/rollback-contract.md` defines the
snapshot/restore boundary and evidence required before one can be added.
