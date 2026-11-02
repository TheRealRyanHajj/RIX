# Easy3D architectural decisions

## ADR-0001: Phase 0 dependencies use pinned CMake acquisition

- **Status:** Accepted for Phase 0
- **Date:** 2026-11-01

### Context

The approved plan permits either a vcpkg manifest or pinned CMake integration. This machine has no vcpkg or Conan installation, while editable Python builds need one reproducible entry point.

### Decision

Use CMake `FetchContent` with immutable upstream Git commit hashes for SDL3, bgfx and its required companion repositories. Use scikit-build-core's declared build-system requirements for pybind11. Keep dependency targets private to the native implementation and expose no third-party types in the public core header.

### Consequences

- A clean checkout can configure without installing a separate dependency manager, provided Git and network access are available.
- First configure is slower and requires access to the pinned upstream repositories.
- Updating any dependency is an explicit reviewed pin change with license-notice review.
- This does not alter future entity, physics, or multiplayer architecture.

## ADR-0002: D3D11 is explicit; interactive graphics are not automated

- **Status:** Accepted for Phase 0
- **Date:** 2026-11-01

### Decision

Phase 0 requests bgfx `Direct3D11` explicitly and fails with an `EngineError` if
that backend cannot initialize. The SDL window and bgfx device exist only for
the duration of `Engine.run()`, with bgfx shutdown occurring before the HWND is
destroyed and SDL quits. GPU/window checks remain manual or explicitly invoked
visible diagnostics; neither pytest nor CTest registers them.

### Consequences

- CI cannot report a graphical pass merely because non-GPU tests pass.
- `Game` construction and all default unit tests remain display-independent.
- Backend fallback/selection is deferred until it is tested rather than making
  an unsupported Vulkan or OpenGL claim.

## ADR-0003: Keep bgfx rendering on the SDL window thread in Phase 0

- **Status:** Accepted for Phase 0
- **Date:** 2026-11-01

### Context

Easy3D supplies an SDL-owned Win32 `HWND` to bgfx and owns the event loop. Phase
0 has no render-job system, and bgfx supports selecting single-threaded mode by
calling `bgfx::renderFrame()` before `bgfx::init()`.

### Decision

Initialize, reset, present, and shut down bgfx on the SDL/window thread. Preserve
the complete `bgfx::Init::swapChain` defaults when retaining the descriptor for
resize resets; a standalone `bgfx::SwapChain` intentionally starts with sentinel
formats and is not a complete primary swap-chain configuration.

### Consequences

- Win32 window, D3D11 device, swap-chain, and SDL event ownership have one clear
  thread-affinity rule.
- The Phase 0 implementation avoids a renderer thread that provides no current
  scheduling benefit.
- A future render-thread architecture requires a deliberate lifecycle redesign
  and new resize/shutdown tests; this choice does not constrain entity, physics,
  or multiplayer state ownership.

## ADR-0004: Record VS 2026 validation without raising the intended minimum

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

The plan names Visual Studio 2022/MSVC v143 as the baseline. The machine became
equipped with Visual Studio Build Tools 2026 v18.11.3, MSVC 19.51, and Windows
SDK 10.0.26100.0, but not the older compiler.

### Decision

Use the installed toolchain to complete Phase 0 validation and document its
exact versions. Keep Visual Studio 2022/MSVC v143 as the intended minimum rather
than claiming it was tested or unnecessarily increasing the project minimum.

### Consequences

- Debug/Release and Python 3.11 evidence is genuine for MSVC 19.51.
- Compatibility with the VS 2022 baseline remains a documented validation limit
  until that compiler runs the same presets and tests.

## ADR-0005: World-scoped generational entity handles

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Entity wrappers must survive ordinary Python reference patterns without exposing
native pointers, and recycled native storage must never make a destroyed wrapper
silently refer to a new entity. Future network identity must remain separate
from process-local storage identity.

### Decision

Each native `World` receives a nonzero 64-bit runtime ID and owns reusable entity
slots. `EntityHandle` stores world ID, 32-bit slot index, and nonzero 32-bit
generation. Destroy and scene-clear operations advance generations before reuse.
All state access validates the full handle. Python `Entity` wrappers retain their
owning `Scene`; `Game` owns at most one active scene and scene ownership is
exclusive between games.

### Consequences

- Stale and cross-world references fail with `InvalidEntityError` rather than
  aliasing memory or crashing.
- Slot reuse is O(1), while entity enumeration is currently O(slot capacity).
- `Entity.id` is generation-qualified only within its scene and is explicitly
  not a future network ID.
- World mutation is gameplay-thread-only until later scheduler/threading work
  adds explicit synchronization boundaries.

## ADR-0006: Easy3D math boundary with private GLM transform implementation

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

GLM is the locked internal math dependency, but beginner-facing APIs must not
leak third-party types. Entity vector component edits such as
`entity.position.x += 1` must persist rather than mutate detached temporaries.
Euler angles also have multiple valid representations for one orientation.

### Decision

Pin GLM 1.0.1 by commit and link it privately. Native Easy3D `Vec2`, `Vec3`,
`Quat`, and `Transform` values own the C++ API boundary. Python exposes
Easy3D-owned value types; entity local position, Euler rotation, and scale use
live proxy instances whose component setters write through to native state.
Native transform slots store quaternion rotation, local TRS, hierarchy links,
cached world matrices, and recursive dirty state.

Local matrices use translation × rotation × scale in a right-handed, +Y-up,
-Z-forward convention. Reparenting preserves local transforms by default and
offers explicit keep-world decomposition. Euler angles are a degree-based facade;
orientation equality is quaternion-based because Euler triples are not unique.

### Consequences

- No GLM object appears in Python or stable Easy3D headers.
- Cached descendant transforms recompute only after ancestor/local changes.
- Direct component mutation on entity vector properties is persistent.
- Keep-world TRS decomposition cannot represent arbitrary shear exactly; future
  APIs must not imply general affine/shear support without changing storage.

## ADR-0007: Backend-neutral mesh data and reviewed D3D11 shader artifacts

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Phase 1.3 requires genuine indexed GPU geometry and deterministic resource
lifetime without leaking bgfx handles into beginner or stable native APIs. The
pinned bgfx CMake integration can build `shaderc`, but enabling it adds roughly
690 shader-tool dependency compilation steps per fresh configuration, including
SPIR-V, glslang, and Tint code not needed by the current D3D11 runtime.

### Decision

Keep `MeshData`, `Material`, and related values backend-neutral. A private
`BgfxRenderer` owns a mesh lifetime manager, programs, uniforms, and submission.
Normal Windows builds consume reviewed Shader Model 5 DXBC headers committed
beside Easy3D-owned `.sc` sources. `EASY3D_REGENERATE_SHADERS=ON` explicitly
builds the immutable-pinned bgfx `shaderc` and regenerates those headers for
review. Only the supported D3D11 profile is generated at this stage.

The Phase 1.3 geometry scene is an opt-in native diagnostic, not a hidden default
world or a substitute for the Phase 1.4 camera and Phase 1.7 render components.

### Consequences

- Clean editable, Debug, and Release runtime builds avoid compiling unused
  shader tooling while remaining independent of a globally installed compiler.
- Source changes require explicit regeneration and review of deterministic
  binary-header diffs.
- GPU buffers and shaders cannot escape the renderer lifetime, and shutdown
  orders all releases before bgfx/device destruction.
- Additional renderer backends require their own generated artifacts and
  runtime evidence before they can be claimed.

## ADR-0008: Camera matrices use an Easy3D-owned column-major boundary

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Camera projection must be independently testable without exposing GLM or bgfx
types. D3D and OpenGL-family backends also differ in normalized depth range, and
high-DPI SDL windows distinguish logical dimensions from drawable pixel size.

### Decision

Expose Easy3D-owned `Camera` and `Matrix4` native values. Matrices are
column-major; coordinates are right-handed, +Y up, and camera-forward -Z.
Perspective projection takes vertical FOV; orthographic projection takes a
fixed vertical height. Both take explicit near/far planes, aspect, and a
renderer-capability `homogeneous_depth` choice. The D3D path maps depth to
`[0,1]`; homogeneous depth maps to `[-1,1]`.

The renderer retains current pixel width/height and calculates aspect on every
geometry submission after SDL size events. Python exposes the same native math
through a typed standalone `Camera`; entity/component attachment is deferred
until that ownership API exists.

### Consequences

- GLM remains private while native and Python tests can inspect exact matrices.
- Resizing changes horizontal projection without distorting vertical FOV or
  orthographic height.
- A camera can be configured and validated before scene components are added,
  without inventing implicit global-camera ownership.
- Multi-camera render targets are not claimed.

## ADR-0009: Canonical CPU texture cache with private GPU resources

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Texture decoding and sharing must work through stable Easy3D types without
exposing bgfx handles. Color-space choice changes GPU interpretation, while
sampler choice changes sampling rather than decoded bytes. A future asset
scheduler will need deterministic keys and thread-safe access.

### Decision

Decode `.png`, `.jpg`, and `.jpeg` through the immutable-pinned bimg decoder to
engine-owned RGBA8 `ImageData`. The shared CPU `TextureCache` key is a canonical
absolute path plus linear/sRGB intent; Windows keys are case-folded. Cache
access is mutex-protected and synchronous. Missing files use a distinct
`MissingAssetError`; malformed and unsupported inputs use `AssetError`.

Keep min/mag/mip filtering and U/V wrapping in backend-neutral
`TextureSampler`. The private bgfx manager maps those values and sRGB intent to
creation flags, owns move-only handles, and releases all textures before
programs and renderer shutdown. Runtime builds consume reviewed Shader Model 5
textured-shader headers generated from committed Easy3D shader sources.

UV `(0,0)` addresses the first/top-left decoded texel, with U rightward and V
downward. This matches the supported D3D11 path and is now part of the mesh
contract.

### Consequences

- Repeated canonical path/color-space requests share decoded storage; sampler
  variants do not duplicate CPU pixels.
- GPU resources remain private and cannot outlive the renderer.
- Clearing a cache drops its ownership but not outstanding shared references.
- Loading is intentionally synchronous; asynchronous scheduling and eviction
  policy remain later asset-system work.
- Other renderer backends must explicitly adapt or transform the documented UV
  convention and receive independent shader/runtime validation.

## ADR-0010: Convert tinyobjloader output into immutable Easy3D model assets

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

OBJ support must preserve the engine's public type boundary, share parsed mesh
resources, work in a future headless server/tool process, and provide predictable
behavior for incomplete normals and broad MTL syntax.

### Decision

Pin tinyobjloader `v2.0.0rc13` by immutable commit and link it privately. Convert
every successful parse into Easy3D-owned immutable `ModelData`, `ModelPart`,
`ModelMaterial`, and `MeshData`. Triangulate faces and group parts by both OBJ
shape and material. Normalize supplied normals; when a triangle has incomplete
normals, generate one flat geometric normal and unique vertices. Flip OBJ V into
the existing top-left texture convention.

Cache models strongly by canonical absolute OBJ path, with Windows case folding.
The implemented MTL surface is deliberately narrow: diffuse color/alpha and one
diffuse texture. Resolve texture paths against the OBJ directory and fail on
missing MTL/texture/material references instead of silently substituting a
default. Retain non-fatal parser warnings on `ModelData`.

### Consequences

- Repeated model instances can share one parsed model and its mesh arrays; GPU
  handle sharing attaches to these resources with Phase 1.7 components.
- OBJ parsing remains usable in graphics-disabled/headless builds.
- Smooth shading requires source normals; absent normals are visibly flat.
- Advanced MTL fields, relative-to-nested-MTL texture roots, glTF, animation,
  and PBR are explicitly outside this milestone.

## ADR-0011: Native scene traversal with guarded Phase 1 mutation

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Phase 1.7 must render Python-created entities without a per-entity Python call on
every frame. `Engine.run()` releases the GIL while the native window loop is
active, so uncontrolled mutation from another Python thread would race native
renderer traversal before the Phase 2 gameplay scheduler exists.

### Decision

Store a singleton optional `RenderComponent` in each native world slot. Built-in
primitive components share process-lifetime immutable meshes; model and image
components retain shared cache allocations. A loaded `Game` keeps the Python
`Scene` alive and gives `Engine` a non-owning native pointer. The renderer walks
the active scene, reads native world transforms, and caches GPU meshes by
immutable resource identity and textures by image identity plus sampler.

Reject public Python scene/entity/component mutation while the owning game is
running. Scene changes remain legal before and after a run. This is an explicit
temporary boundary, not a claim that gameplay must be static forever; Phase 2
will introduce ordered mutation/update phases.

### Consequences

- Rendering does not cross the Python/native boundary per entity or per frame.
- CPU and GPU geometry are shared across primitive/model instances and released
  under existing renderer/world ownership rules.
- The non-owning native pointer is safe under `Game` because its `_scene`
  reference is strong and replacement/unload are rejected during a run.
- Runtime animation and gameplay mutation are deferred until the scheduler can
  serialize them against native traversal.

## ADR-0012: Scene-value camera, native baseline lights, and transient debug lines

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Phase 1.8 needs a beginner-facing camera and lighting surface without coupling
view state to an entity-component design that later gameplay/editor work may
need to refine. Lighting must remain entirely native per frame, behave correctly
under transform hierarchy and non-uniform scale, and preserve useful output for
existing scenes. Debug visualization should not retain avoidable GPU resources.

### Decision

Store one validated `Camera` value and persistent `DebugLine` array on `Scene`.
Store singleton ambient/directional `LightComponent` values on world entity
slots. Ambient lights accumulate; the first enabled directional light uses the
entity's world-space local -Z direction. A default contribution remains for a
light kind until an explicit component of that kind exists.

Add `Material::lit` and pass inverse-transpose normal rows plus material and
lighting uniforms into reviewed Shader Model 5 solid/textured shaders. Render
debug lines unlit in depth-tested and overlay batches using bgfx transient
vertex buffers. Python camera assignment is copy-in/copy-out, and all public
mutation retains the Phase 1 running-game guard.

### Consequences

- Existing no-light scenes remain visible while explicit lights have simple,
  deterministic semantics.
- Non-uniform scaling does not corrupt Lambert normals, and unlit materials
  provide a basic emissive/debug presentation without claiming a full material
  model.
- Only one directional light contributes; shadows, PBR/specular response,
  transparent sorting, and multi-light selection are later rendering work.
- Debug lines consume no persistent GPU handles but remain CPU-persistent until
  cleared. A later diagnostics system can add per-frame lifetimes and shapes.
- Cameras are scene values rather than entities for now; future multi-camera or
  editor requirements require a separate reviewed ownership decision.

## ADR-0013: Conservative bounds culling and compatibility-keyed instancing

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Phase 1.9 must reduce avoidable CPU/GPU submission while retaining correct
transforms, lighting normals, resource sharing, and a measurable public result.
Exact oriented-box culling is unnecessary for the initial static-scene target,
while unconditionally instancing non-uniform scale would invalidate the existing
inverse-transpose normal transform.

### Decision

Cache each immutable mesh's local AABB and derive a conservative world-space
bounding sphere from its center, extents, hierarchy transform, and scale. Build
six normalized planes from projection × view using the active backend's depth
convention, then reject only spheres wholly outside a plane.

Group visible mesh parts by GPU mesh handle, complete material value, and GPU
texture handle. Groups of at least two with uniform absolute XYZ scale use a
transient bgfx instance buffer containing one column-major model matrix per
instance and dedicated instanced vertex programs. Other groups retain the exact
single-draw path. Publish coherent latest-frame draw/visibility/instancing
counters through a sequence-protected atomic store.

### Consequences

- Frustum testing is cheap and conservative; edge objects may remain visible,
  but visible objects are not intentionally rejected.
- Common static primitives collapse to one draw per compatibility group, while
  material/texture differences correctly split batches.
- Non-uniform scale remains correct at the cost of individual submission.
- Batches are rebuilt each frame and use transient memory. Persistent instance
  buffers, spatial trees, occlusion culling, and parallel visibility remain
  possible later optimizations after profiling.
- Renderer counters count mesh parts, not high-level entities, and are suitable
  for diagnostics rather than gameplay synchronization.

## ADR-0014: Platform-neutral input state with SDL-owned event translation

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Input must support SDL keyboard, mouse, and gamepad events without exposing SDL
types to the stable native or Python APIs. `Engine.run()` releases the GIL, so
pointer-lock requests and diagnostic reads can race the window loop unless the
ownership boundary is explicit. Focus loss must not leave controls stuck.

### Decision

`Engine` owns a mutex-protected, platform-neutral `InputSystem` built in both
graphics and headless configurations. Controls use canonical `device:name`
identifiers and feed remappable scalar actions with scale and deadzone values.
The SDL window thread alone owns SDL objects, translates events, opens one
primary gamepad, applies relative mouse mode, and resolves action transitions
after event polling.

Pointer lock is a declarative request plus a separately reported applied state.
Focus loss zeros held controls and drops the applied lock; focus gain can
reapply the retained request. Python receives immutable snapshots and never an
SDL event pointer.

### Consequences

- Action-map and focus behavior are unit-testable without a window or GPU.
- Monitoring threads can safely inspect input while the native loop owns event
  production, though deterministic gameplay reads wait for Phase 2.2 callbacks.
- Physical scancode identifiers are layout-position based; text entry will be
  a separate API when UI work requires it.
- One primary gamepad is sufficient for the initial gameplay milestone.
  Multi-gamepad assignment, rumble, sensors, and controller UI labels remain
  later extensions.

## ADR-0015: Python lifecycle callbacks execute inside the native frame boundary

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Python gameplay must mutate the native scene without racing renderer traversal.
Moving SDL to a background thread would weaken platform ownership and introduce
cross-thread scene access. Holding the GIL for the whole native window loop
would block monitoring and stop requests.

### Decision

Keep SDL event polling, gameplay scheduling, and rendering serial on the thread
that calls `Game.run()`. Pybind releases the GIL while the native loop works and
reacquires it only for a frame callback placed after input polling and before
renderer submission. `Game` records the callback thread/scope, and scene
mutation permits that exact boundary while rejecting other running-game access.

The Python scheduler owns `awake`/`start` state, a clamped fixed-step
accumulator, catch-up limits, render hooks, exception policy, and per-hook
profiles. Destroy and clear operations queue to phase boundaries; normal
property/component/camera writes apply immediately because native traversal is
not concurrent.

### Consequences

- SDL remains on its owning thread, Python scripts have the GIL, and renderer
  traversal cannot overlap script mutation.
- Python callback cost directly affects frame time and is therefore measured.
- Fail-fast errors unwind C++ RAII normally; tolerant mode quarantines a broken
  script after logging its traceback.
- The scheduler defines ordering, not deterministic arbitrary Python behavior.
- Physics and networking must insert their owned stages into this boundary or
  communicate through queues; they must not invoke Python from worker threads.

## ADR-0016: Caller-owned utilities use explicit clock domains

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Timers and interpolation become ambiguous once render frames, fixed simulation
ticks, headless servers, pause behavior, and real elapsed time coexist. A global
utility manager would also hide ownership and complicate scene teardown.

### Decision

Keep `StateMachine`, `Timer`, `Cooldown`, `EventBus`, and `Tween` as pure-Python,
caller-owned objects. Timing objects declare `wall`, `render`, or `simulation`
ownership and reject incompatible advancement. Wall time is explicitly polled;
render/simulation time is explicitly advanced by its owning callback. Event
dispatch remains synchronous and deterministic, with stable priority order and
bounded recursion. State transitions reject callback reentrancy.

### Consequences

- Utilities run in headless tests without SDL, bgfx, a scene, or native setup.
- Pause and time-scale policy remains explicit at the call site instead of
  leaking wall time into deterministic fixed-step mechanics.
- There is no implicit global bus or timer lifecycle to leak across worlds.
- Later engine-managed conveniences can wrap these primitives without changing
  their timing and exception semantics.

## ADR-0017: Lazy per-scene Jolt worlds behind Easy3D handles

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Physics must work in headless servers, stay independent of renderer lifetime,
reject stale/cross-world references and advance on simulation time rather than
render time. Creating Jolt's default buffers for every render-only scene would
also impose avoidable memory cost.

### Decision

Pin Jolt 5.6.0 by immutable commit and statically link a CPU-only baseline-SSE2
build. Register Jolt process support once, but lazily give each used `Scene` an
independent `PhysicsWorld`. Keep Jolt types private behind Pimpl and expose
world/generation-checked Easy3D body handles. Begin with Jolt's single-threaded
job system so `PhysicsSystem::Update` completes on the simulation thread before
the scheduler proceeds. Step after Python `fixed_update` using the exact fixed
delta; scene clear owns body teardown.

### Consequences

- Physics tests run without SDL/bgfx/GPU and scenes that never use physics do
  not allocate a physics system or its temporary buffer.
- Different scenes have independent gravity, bodies, capacities and handles.
- Baseline CPU compatibility is favored over AVX-specific optimization.
- The initial single-threaded job backend is safe and predictable but not a
  final performance claim; parallelism requires an owned engine job adapter.
- Easy3D-owned component/handle layers can extend this foundation without ever
  leaking Jolt objects into Python.

## ADR-0018: Entity-owned physics components and solver transform precedence

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Python gameplay needs safe collider/body facades without exposing Jolt objects.
Entity lifetime, body lifetime and transform ownership must remain unambiguous,
especially when render callbacks and fixed simulation ticks run at different
rates.

### Decision

Store collider and optional rigid-body configuration in a scene-owned native
table keyed by generation-qualified entity ID. A collider creates one Jolt body;
attaching or removing rigid-body motion replaces it transactionally. Static and
kinematic entity pose changes push to Jolt. Dynamic bodies own their entity pose
after every physics step, and scripts must use an explicit teleport operation
for discontinuous changes. Reject parenting of physics entities until moving
parent transforms have a defined conversion policy.

Expose immutable construction-time box/sphere geometry and material values,
plus dynamic velocity, force, impulse and teleport operations. Keep trigger
event delivery and queries in Phase 2.6 rather than implying callbacks from
sensor configuration alone.

### Consequences

- Destroying an entity deterministically destroys its body and stale Python
  facades fail through the entity handle checks.
- Render-frame scripts cannot accidentally fight a dynamic solver body through
  ordinary transform assignment.
- Primitive `collider=True` remains beginner-friendly while rigid-body motion is
  explicit and inspectable.
- Runtime shape/material reconfiguration, physics parenting and advanced shapes
  remain intentional future APIs rather than unsafe partial behavior.

## ADR-0019: Snapshot physics queries and deferred contact dispatch

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Jolt contact listeners may run while bodies are locked and, with a future job
system, from worker threads. Calling Python or mutating scene state there would
violate GIL/thread ownership and can deadlock. Query collectors likewise contain
Jolt IDs and temporary storage that must not escape the native call.

### Decision

Convert query collectors synchronously into immutable Easy3D snapshots with
generation-checked entity identity, explicit filtering and deterministic sort
orders. Contact listeners copy a bounded native event record only. Drain those
records after each completed fixed physics step and pose sync, then dispatch
per-recipient Python snapshots through the normal scheduler callback path.

### Consequences

- Python never runs from a Jolt callback and never retains a Jolt body pointer.
- Collision and trigger callbacks share lifecycle, profiling, exception and
  deferred-mutation rules with other gameplay hooks.
- Query results remain safe after the native collector is destroyed; normal
  entity stale-handle checks still apply if a result is retained too long.
- Event queue exhaustion is an explicit `PhysicsError`, not unbounded memory
  growth or silent loss.

## ADR-0020: Jolt virtual characters with native command/state boundaries

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Player collision, grounded state, slopes, steps and jumping must run at the
fixed physics rate and later support authoritative/predicted commands. A Python
transform loop would duplicate collision logic and make network reconciliation
unsafe, while exposing Jolt objects would break the engine boundary.

### Decision

Own `CharacterVirtual` motors inside each `PhysicsWorld` behind
generation-checked handles. Python submits bounded movement/heading/jump
commands and reads copied state only. Use a bottom-aligned capsule plus a
smaller inner body on the character layer. Run `ExtendedUpdate` before the
rigid-body update, with explicit acceleration, air control, jump, slope and
step settings. First-person follows command heading; third-person faces
movement. Scene pose synchronization occurs only after the native step.

### Consequences

- Character movement remains headless and no Jolt callback enters Python.
- The input/state boundary can gain sequence numbers and replay in Phase 5.1
  without replacing the collision motor.
- Characters participate in normal queries, body collision, sensors and copied
  contact events through their inner body.
- Camera pitch/offset/obstruction remain explicit game-side behavior.
- Runtime resizing/tuning and character parenting require future transactional
  APIs rather than implicit shape mutation.

## ADR-0021: Construction-time advanced shapes, owned joints, and opt-in CCD

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Advanced collision must cover authored static levels, dynamic convex objects,
fast projectiles and basic connected bodies without leaking Jolt allocation or
lifetime rules. Concave moving meshes and an unbounded joint catalogue would
expand the first correctness milestone beyond testable ownership semantics.

### Decision

Add capsules, bounded convex hulls and static OBJ triangle meshes as immutable
collider construction data. Bake model scale once at body creation. Expose
linear-cast CCD as a dynamic rigid-body option. Own fixed and distance
constraints in the physics world behind generation handles and mirror endpoint
ownership in `Scene`; endpoint replacement/destruction cascades constraint
removal.

### Consequences

- Headless tests exercise actual mesh/hull/capsule solver contacts, joint
  invariants and a discrete-versus-linear-cast tunneling control.
- Static concave levels and ordinary ropes/welds need no user C++.
- Runtime shape edits rebuild components explicitly rather than mutating solver
  data beneath active contacts.
- Compound, moving concave, hinge/slider/motor/breakable APIs remain scoped
  follow-up work and are not implied by this milestone.

## ADR-0022: Bounded polled transport boundary with deterministic simulation

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

The socket backend will eventually own native callbacks and possibly a worker
thread, while Python gameplay and scenes have a single owning thread. Transport
pressure, malformed sizes and callback bursts cannot be allowed to create
unbounded memory growth or enter Python from an uncontrolled native thread.
Loss and latency behavior also need repeatable tests before a platform socket
dependency is introduced.

### Decision

Define a dependency-neutral `NetworkTransport` data-plane interface around
opaque 64-bit connection IDs, copied transport events, explicit delivery intent
and send status. Cross the worker/gameplay boundary through a mutex-protected
FIFO queue with a fixed capacity; surface overflow as `NetworkError`. Provide a
seeded, manually advanced two-endpoint datagram simulator implementing the same
interface. Keep address/listen/connect creation on future concrete transports
and higher-level client/server owners rather than forcing backend lifecycle into
the data plane.

### Consequences

- Queue capacity, payload size, loss, delay, ordering, disconnect and statistics
  are testable headlessly with no renderer or network access.
- Future GameNetworkingSockets callbacks copy bounded data and return; Python
  observes it only when the gameplay thread polls.
- A connection ID is local opaque transport state, not a replicated entity ID
  or authenticated player identity.
- The simulator deliberately does not implement retransmission, encryption,
  sockets, protocol framing or authority. Those capabilities are not implied by
  a reliable delivery label and remain later milestones.

## ADR-0023: Static direct-IP GameNetworkingSockets backend

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

GameNetworkingSockets needs generated Protobuf messages and cryptographic
primitives. Mixing an arbitrary host `protoc` with a different runtime risks
wire/runtime incompatibility, and adding OpenSSL solely for Windows expands the
redistributable and audit surface. The library also owns process-global state,
while Easy3D objects may overlap in lifetime.

### Decision

Fetch immutable GameNetworkingSockets 1.6.1 and Protobuf 5.29.3 revisions and
build their static libraries together as C++17. Generate messages with the
matching source-built `protoc`. Use the supported Windows BCrypt provider for
AES/SHA and upstream Donna code for Curve25519/Ed25519; disable ICE/WebRTC,
tools, examples and upstream tests. Keep all backend types private and own
initialization through a mutex-protected process reference count. Validate the
backend with exact-byte reliable socket-pair round trips in native and Python
tests. MSVC is the supported Windows toolchain; a MinGW build remains a
diagnostic path after encountering an upstream GCC 15 Protobuf `musttail`
failure.

### Consequences

- The dependency graph, generated-code/runtime pairing and license inventory
  are reproducible from a clean checkout.
- Easy3D does not redistribute OpenSSL or expose third-party socket handles.
- Multiple runtime owners shut down safely only after the last owner leaves.
- This milestone proves backend operation, not a public listener/client API,
  wire handshake, identity, authentication or replication.

## ADR-0024: Fixed bounded three-message connection handshake

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

The live transport needs to reject incompatible or malicious peers before any
gameplay schema is decoded. Protobuf is a private dependency of the selected
transport and does not by itself define Easy3D compatibility, roles, resource
limits or safe disconnect diagnostics. A server also needs evidence that a
client received and retained the negotiated limit before treating it as ready.

### Decision

Use an Easy3D-owned 12-byte little-endian envelope with fixed magic, wire-format
version, message type, zero reserved flags and exact payload length. Cap every
handshake frame at 512 bytes. Exchange a client hello, server acceptance and
client confirmation over reliable transport messages. Each peer declaration
contains exact application protocol/schema versions, an explicit client/server
role and a message-size limit; negotiate the smaller limit and cap declarations
at 1 MiB. Encode rejections as stable numeric disconnect codes with 1–256 bytes
of validated UTF-8 text that excludes control characters. Treat local API
misuse as a programming error, but convert every untrusted parse/state failure
into a bounded rejection.

### Consequences

- Compatibility and resource bounds are established before application data.
- The server does not reach established state until it verifies the client's
  confirmation of the accepted limit.
- The codec is independent of GameNetworkingSockets, addresses and clocks, so
  it can be tested deterministically and reused by future transports.
- Wire-format or schema evolution requires an explicit versioned policy; format
  1 intentionally supports exact matches only.
- Transport encryption does not authenticate a player identity, and the
  handshake does not claim authentication, discovery, sockets or replication.

## ADR-0025: Poll-owned asynchronous direct-IP client

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

GNS connection transitions arrive through native callbacks, while Easy3D
gameplay and Python have a single owning thread. Letting callbacks enter Python
would make scene mutation timing uncontrolled. A blocking `connect()` would
also freeze a game loop and make timeout/cancellation behavior difficult to
compose. DNS and discovery introduce policy and attack surfaces separate from
the direct-IP foundation.

### Decision

Make `NetworkClient`/`easy3d.network.Client` an asynchronous, single-owner
direct numeric IPv4/IPv6 endpoint. `connect()` creates one GNS connection and
returns; `poll()` alone runs GNS callbacks, copies at most 256 messages, drives
the Phase 3.3 reliable handshake, enforces one monotonic connection/handshake
deadline, reports queue overflow, and drains events. Use per-connection GNS user
data to route callbacks to native state, clearing it before close/destruction.
Publish Python callbacks only while the Python caller processes polled events.
Invalidate the opaque local connection ID on close, preserve stable Easy3D
disconnect codes and retain unknown backend codes as integers. Expose both
application counters and GNS observational ping/rate/queue metrics.

### Consequences

- No native callback calls Python or mutates scene/gameplay state.
- Games must poll regularly; timeout and callback progress intentionally follow
  that owning-thread pump.
- Numeric addresses keep this milestone deterministic and bounded. DNS, LAN
  discovery and firewall guidance remain explicit later work.
- The client is usable against a compatible peer, but the public authoritative
  listener and headless server remain Phase 3.5 rather than a hidden test API.

## ADR-0026: Poll-owned native listener with a Python fixed-rate headless owner

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

A dedicated server must accept multiple peers and run the same Python gameplay
lifecycle/native physics used by a game without creating SDL or bgfx. GNS
listener callbacks arrive through process-global callback pumping, incomplete
handshakes can consume resources, and `CloseListenSocket` ungracefully closes
accepted connections. Python must remain on one deterministic gameplay thread,
while an operator or test still needs to request shutdown from another thread.

### Decision

Give `NetworkServer` one numeric direct-IP listener, one poll group, a bounded
peer map and a shared bounded application event queue. Count handshaking peers
against the configured maximum. Give every peer a monotonic local ID, Phase 3.3
server handshake, deadline and negotiated payload cap; publish it only after
client confirmation. Route callbacks through inherited per-connection GNS user
data, clear that pointer before close, and keep `poll()` as the sole callback/
message pump. Close accepted peers before the listener so remote clients retain
the stable server-stop reason.

Compose the native transport in Python with the existing `SimulationScheduler`
and exclusive `Scene` ownership. `run()` paces exact fixed ticks, `step()` is a
deterministic one-tick seam, and callbacks execute only on the caller. A
thread-safe event is the sole cross-thread operation used by `stop()`; no other
concurrent server calls are supported.

### Consequences

- Dedicated simulation and physics run in graphics-disabled builds without an
  `Engine`, window, input owner or renderer device.
- Pre-handshake peers are bounded, timed out and invisible to gameplay.
- Python server logic uses the same lifecycle/order as single-player scripts;
  callback exceptions remain visible rather than being swallowed by native
  worker code.
- This is an authoritative dedicated role only. Listen hosts, discovery,
  player identity, replication and cross-process sample guarantees remain
  later milestones.

## ADR-0027: Compose listen hosts from isolated authority and client roles

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

A listen host needs local client behavior and authoritative simulation in one
process. Reusing the authority scene directly from the local client would run
scripts/physics twice, create host-only callback paths and blur transport IDs
with future player/network-object identity. A special in-process data path
would also make host behavior differ from remote direct-IP clients.

### Decision

Compose `ListenServer` from the existing public `Server` and `Client`. Bind the
authority first, then synchronously establish one ordinary loopback client
before returning readiness. The authority alone owns the scene, scheduler and
fixed tick. Pump the client after each completed authority tick. Tag all
composed events with an explicit authority/client role and `local_host` flag;
keep each child's opaque connection namespace intact even when numeric values
match. Additional clients remain ordinary server peers and are tagged as
non-host. Reuse the server's thread-safe stop request and clean up both roles on
partial startup failure.

### Consequences

- Listen hosts exercise the same GNS queues and handshake as remote clients;
  there is no privileged shared-memory protocol path.
- Authoritative scripts and physics execute exactly once per host tick.
- Role tags, not integer equality, determine which transport owns a connection
  ID. This does not yet create player identity or network-object ownership.
- Rendered `Game` attachment, discovery, replication and host prediction remain
  later milestones.

## ADR-0028: Polled bounded UDP query/response for opt-in LAN discovery

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

LAN browsing is useful before the user knows a direct address, but it is not
gameplay transport, authentication or a reason to introduce a service thread.
Broadcast input is untrusted, Windows firewall and adapter policy vary, and a
naive listener/cache can be flooded. GNS remains the supported direct-IP data
plane and already performs the compatibility handshake after connection.

### Decision

Implement an explicitly started, caller-polled IPv4 UDP control plane in the
typed Python package. A browser broadcasts a fixed, random-nonce query from an
ephemeral port; an announcer on a configured discovery port returns one bounded
unicast response containing its instance ID, game port, exact protocol/schema
versions and safe UTF-8 name. Cap datagrams, names, work per poll, per-source
response rate state, response windows, result TTL and cache capacity. Require
the source discovery port and current nonce, but make no authentication claim.
Never auto-connect, resolve DNS, change firewall state or route discovery.

### Consequences

- Discovery can be enabled or omitted without changing dedicated/listen server
  or client transport ownership.
- Low-frequency socket work remains on the Python owning thread; gameplay bytes
  continue through the native bounded GNS backend.
- Limited/directed broadcast can be blocked by firewalls, VPNs, guest-network
  isolation and routers. Numeric direct IP is the documented fallback.
- IPv6 discovery, mDNS/directory/relay services, authentication and
  separate-machine evidence are not implied by this local IPv4 milestone.

## ADR-0029: Process-boundary transport gate with explicit peer liveness

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Same-interpreter loopback proves protocol behavior but not extension loading,
socket ownership or teardown across real process boundaries. Abrupt process
loss cannot use Easy3D's graceful close reason, and the upstream connected-peer
timeout needs an engine-owned policy separate from handshake deadlines. Tests
must also distinguish client confirmation from the server's later validated
establishment event.

### Decision

Ship one public-API-only command with independent server/client roles and a
fixed bounded request/reply. Add finite positive `peer_timeout` configuration to
the native client and listener, mapped to GNS `TimeoutConnected`, with a
10-second default and no process-global mutation. In integration tests, publish
separate bind, client-connected and server-connected markers; terminate the
opposite process only after the relevant establishment marker. Bound and reap
every subprocess. Treat backend/OS abrupt-failure codes as observational while
requiring an application disconnect event.

### Consequences

- Clean exchange, gameplay-port collision and abrupt loss in both directions
  exercise the installed native extension across Windows processes.
- Peer timeout is a liveness policy, not an exact callback deadline; polling and
  backend scheduling remain part of observation latency.
- The sample can be run on a LAN with numeric addressing and firewall policy,
  but two-physical-machine execution remains separately reported evidence.
- Process transport success does not imply replication, RPC, player identity,
  ownership, prediction or rendered-client integration.

## ADR-0030: Explicit prefab schema and authority-monotonic network IDs

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Scene entity IDs are generation-qualified local handles and cannot identify the
same logical object in another scene or a late join. Implicit class names or
registration order are unstable schema, while partially delivered lifecycle
updates cannot be allowed to leave one client silently divergent.

### Decision

Require explicit nonzero uint32 prefab IDs plus unique bounded names in a frozen
registry. Fingerprint the declared schema version and canonical ID/name mapping.
Let one server attachment allocate monotonically increasing nonzero uint64
network-object IDs without reuse. Send fixed reliable begin/spawn/end snapshots
on connect and fixed spawn/despawn updates afterward. Disconnect a peer on
replication backpressure or invalid lifecycle data so reconnect can reapply a
complete snapshot. Preserve existing application callbacks and reject
client-authored lifecycle frames.

### Consequences

- Network IDs remain stable across authority/client scenes and late join but
  only within one authority session; persistence across server restarts is not
  claimed.
- Prefab mapping mismatches fail before client entities are accepted.
- Lifecycle factories can create typed entities without serializing Python
  objects or exposing scene handles on the wire.
- Field state, transforms, ownership, RPCs and relevance require later versioned
  messages and are intentionally absent from this milestone.

## ADR-0031: Frozen typed field schema with authority-only dirty state

- **Status:** Accepted
- **Date:** 2026-11-01

Declare each network variable in the prefab registry with explicit uint16 ID,
name, wire type, default and byte bound, and include it in the fingerprint.
Normalize authority assignments through the wire codec, increment a per-field
uint64 version only on change, and flush reliable full-field updates. Client
mirrors are read-only and require newer versions. Stream and uniquely account
all current fields in late-join snapshots. This favors bounded correctness and
schema diagnostics before delta compression, ownership or transforms.

## ADR-0032: Replaceable fixed transform stream with bounded interpolation

- **Status:** Accepted
- **Date:** 2026-11-01

### Context

Transforms update more frequently than reliable gameplay fields. Encoding them
as ordinary `NetworkVar` values would add per-field overhead and let a missing
intermediate sample block newer visual state. Client interpolation needs ordered
ticks, bounded storage and a clear policy for packet reordering. Initial
relevance must reduce traffic without making reliable object state disappear.

### Decision

Add one fixed float32 local position/quaternion/scale frame to the frozen prefab
schema. The authority supplies a nondecreasing uint64 tick; each flush assigns a
monotonic sequence and uses unreliable delivery. Clients normalize validated
quaternions, retain a fixed-capacity history, drop older/duplicate samples,
replace newer same-tick samples, and interpolate at an explicit render tick
without extrapolation. An optional per-connection predicate suppresses only
transform sends. Late join receives the current relevant baseline. Bound the
per-client history and authority sends per flush, and expose counters rather
than disconnecting on replaceable queue pressure.

### Consequences

- Lifecycle and authoritative field state remain reliable and independent of
  transient transform loss or relevance.
- Local transforms are coherent with current unparented multiplayer actors;
  parent-space replication policy remains future work.
- The predicate is a policy seam, not spatial interest management or a scale
  claim. Prediction, reconciliation, baseline ACK/resync and bandwidth priority
  remain Phase 5 work.
