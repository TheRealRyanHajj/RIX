# Easy3D known issues and validation limits

There are no remaining blockers to the Phase 0 exit gate on the validated
machine.

## Phase 1 exit gate is complete

Phase 1.1–1.10 are implemented, including native scene traversal, public
primitive/model render entities, scene camera ownership, directional/ambient
lighting, debug lines, conservative frustum culling, compatible-mesh hardware
instancing, frame counters, perspective/orthographic projection, the first-world
example, and the recorded 10,000-cube workload. Phase 2.2 now drives the
first-world orbit camera at a safe frame boundary, completing the remaining
moving-camera exit evidence.
The baseline lighting intentionally supports ambient accumulation and one
directional light; shadows, PBR, multiple directional-light blending, and
transparent sorting remain later work.

Instancing currently requires identical mesh, material, texture/sampler, and
uniform absolute scale. Non-uniform scale falls back to individual draws so the
inverse-transpose normal path remains exact. Culling uses a conservative sphere
derived from each cached local AABB; it can retain edge objects but must not
reject visible ones. The instanced D3D11 programs compiled and ran with correct
frame counters, but their last dedicated computer-use image inspection was
interrupted, so that specific image is not claimed as visually verified.

Public scene mutation is permitted only on the gameplay thread while a
scheduler callback is active. Other threads remain rejected while `Game.run()`
is traversing the scene; bypassing the public API through the private extension
is outside the supported contract.

Phase 2.3 utilities are caller-owned and are not automatically advanced by the
scheduler: simulation objects belong in `fixed_update`, render objects in
`update`, and wall objects require `poll()`. This is an explicit ownership rule,
not an engine-managed timer service.

The Jolt job backend is deliberately single-threaded. It establishes correct
headless ownership/fixed stepping but is not a physics throughput claim. The
completed Phase 2 physics surface includes box/sphere/capsule/convex/static-mesh
colliders, rigid bodies, materials, forces/impulses, triggers, linear-cast CCD,
and fixed/distance constraints. Queries cover ray, sphere/capsule cast, and
box/sphere overlap, but do not yet include convex casts or arbitrary mesh query
shapes. Physics entities cannot be parented until moving-parent pose
synchronization has a tested contract. Compound subshape contact aggregation is
also deferred with compound shape support.
Collider dimensions and material values are construction-time state in Phase
2.5. Later entity scaling does not silently rebuild Jolt shapes; callers must
remove and recreate a collider when its physical geometry changes.

Phase 2.7 character radius, height and motor tuning are likewise
construction-time state. Character entities cannot be parented or also own an
ordinary collider. The first-/third-person distinction covers native movement
and facing; camera placement, pitch, spring arms and obstruction avoidance are
intentionally Python/game configuration rather than hidden motor policy.

Phase 2.8 triangle-mesh colliders are static, one-sided OBJ geometry; moving
concave meshes are rejected. Convex hulls are capped at 256 source points and
do not perform authoring-time simplification. Fixed and distance joints are the
initial constraint set; hinge, slider, motors, break thresholds and compound
shapes are not yet public. Linear-cast CCD mitigates fast linear tunneling but
does not eliminate the documented extreme-angular-motion case.

Phase 3.8 exposes a numeric direct-IP client, headless authoritative server,
isolated headless listen-host composition, opt-in IPv4 LAN discovery and a
supported two-process byte-exchange sample. There is not yet rendered-`Game`
attachment, DNS, automatic firewall rule, player identity or replication;
those are later work. Transports advance only when
their owning thread polls (the server `run()` loop does this automatically), so
a stalled owning loop also stalls callbacks and deadline enforcement.
Exact protocol/schema equality is the only compatibility policy in wire format
1; migrations or version ranges are not implied.

Python connect/disconnect callbacks are synchronous `poll()` callbacks. If one
raises, the exception propagates after its event was drained and the callback
is not replayed. GNS rate/ping metrics can be zero or `-1` before enough live
traffic exists. Direct transport encryption is unauthenticated and is not a
player/account identity guarantee.

Server bind addresses are numeric only. Binding a LAN-facing game server or the
UDP discovery announcer can cause Windows Firewall to prompt or block inbound
traffic; Easy3D does not create or modify firewall rules. Discovery uses IPv4
limited/directed broadcast and cannot cross routers by design. Guest Wi-Fi
client isolation, VPN routing, virtual adapters and host firewall policy can
hide an otherwise healthy server. Discovery names and endpoints are
unauthenticated LAN input; a matching nonce is request correlation, not
identity. Select a result explicitly and retain numeric direct IP as fallback.
Phase 3.8 is validated over local IPv4 loopback with independent processes,
including bind collision and abrupt termination in both directions. Two
physical machines, actual Defender prompts/rules and routed LAN variations
remain **UNVERIFIED**; the sample supports them but they are not claimed as
executed evidence.

`peer_timeout` configures the GNS connected-peer timeout, but disconnect events
remain poll-driven and backend scheduling/keepalive granularity can add time.
Treat it as failure-detection policy, not an exact callback deadline or a
replacement for gameplay-level heartbeat/AFK rules. Abrupt transport failure
codes can originate in GNS/the OS and are intentionally preserved as integers.

Phase 4.1 replication covers server-owned prefab spawn/despawn and late-join
lifecycle only. Network-object IDs are stable within one authority session but
are not persisted across server restart. Destroy replicated entities through
`ServerReplication.despawn()`; externally destroying a mapped authority entity
does not synthesize a network despawn. Prefab factories must be deterministic
about entity type but no component values or transforms are serialized yet.
Ownership is authority-local for RPC validation and is not yet replicated to
clients. There is no ownership transfer request or resync protocol.

Phase 4.2 adds authoritative `NetworkVar` values, but callers must explicitly
call `ServerReplication.flush()`; it is not scheduler-integrated yet. Values are
reliable full-field updates without delta compression. Client writes and
ownership are intentionally rejected. Transforms are a separate Phase 4.3
stream rather than generic variables.

Phase 4.3 transform flushing is explicitly caller-driven and currently uses
local entity transforms. Relevance is a caller-supplied per-connection
predicate that suppresses transform frames only; it is not a spatial index and
does not hide lifecycle or `NetworkVar` state. Interpolation clamps outside the
bounded history and does not extrapolate, predict or reconcile. Unreliable
queue backpressure is counted and skipped rather than disconnecting the peer;
future baseline recovery/bandwidth scheduling belongs to Phase 5.

Phase 4.4 RPC arguments are limited to the Phase 4.2 primitive wire types and
positional values; vectors, enums, collections and keyword arguments are not
yet schema types. Rate limiting uses a one-second authority-local monotonic
window and drops excess calls without handler execution. Registered handlers
must still validate gameplay conditions such as distance, cooldown, match state
and target visibility. Ownership assignment is server-only and is cleared when
its connection disconnects; it is not yet sent as replica state.

Phase 4.6 match timers are simulation-tick deadlines and must be advanced by
authority game code (normally once per fixed tick); they are not implicitly
wired into every `Server` because games choose when a match clock is paused.
The built-in phase machine carries round/deadline/revision only. Scores, teams,
combat rules and persistence belong to the sandbox/arena milestones.

The Phase 4.7 cooperative sandbox is a finite headless loopback integration
scenario. It validates 2, 4 and 8 local clients but does not attach replication
to a rendered `Game`, simulate WAN impairment, prove physical-LAN behavior or
make a 32-player capacity claim. Movement is authoritative request/replication,
without prediction or reconciliation.

Phase 4.8 resync is explicit/application-triggered; Easy3D does not yet infer a
missing unreliable baseline from acknowledgements. It rebuilds current objects,
fields and relevant transforms but does not preserve client wrapper identity or
reconnect a lost transport/account identity. Automatic ACK/baseline recovery is
Phase 5 work.

Phase 5.1/5.2 prediction deliberately does not choose an RPC/input transport;
applications forward commands and corrections themselves. A full pending queue
raises `NetworkError` instead of silently discarding unacknowledged input.
Replay advances one `CharacterVirtual` against the current collision world; it
does not roll back dynamic bodies, contacts, scripts or the full scene. Remote
players use delayed, clamped Phase 4 transform histories without extrapolation.

The named network conditions are synthetic regression profiles, not measured
ISP/mobile distributions. Seeded `SimulatedLink` is a packet scheduler and does
not retransmit even when delivery metadata says reliable; use scoped backend
impairment when testing real GNS reliability. Backend impairment is process-wide
and therefore rejects overlapping scopes. At 100% loss, application messages do
not arrive, connection establishment/liveness eventually times out, prediction
queues can fill and raise `NetworkError`, and only a later correction/reconnect
can restore authority. Unreliable transforms/inputs rely on newer state or
application redundancy; they are never silently promoted to reliable.

The listen host's local client still traverses the OS loopback transport; it is
not a zero-latency shared-memory shortcut. Its client and authority connection
IDs are separate local namespaces even when their numeric values match. Phase
3.6 does not attach that client to a rendered `Game`, assign a player identity,
or grant host ownership/authorization.

The supported Windows build uses MSVC. A diagnostic attempt with MinGW GCC
15.1 reaches an upstream Protobuf `musttail` compile failure in
`generated_message_tctable_lite.cc`; it is not an Easy3D source failure and is
not bypassed. Use the documented x64 Visual Studio developer environment.

## Input hardware validation

Phase 2.1 action mapping, focus reset, mouse accumulation, pointer-lock state,
and gamepad connect/disconnect behavior are covered by platform-neutral native
tests. The Phase 2.9 D3D11 course received focus and accepted synthetic key
taps, but the automation driver cannot represent held movement and its pointer
capture prevented a reliable border-drag check. Live relative-mouse behavior
therefore remains **UNVERIFIED**. No physical gamepad was connected during this
checkpoint, so real-controller button labels, hot-plug behavior, and axis
hardware are also **UNVERIFIED**. The current API selects one primary gamepad;
multi-gamepad player assignment is not yet exposed.

## Visual Studio 2022 minimum is not independently exercised here

The intended minimum remains Visual Studio 2022/MSVC v143, but the available
and successfully validated compiler is Visual Studio Build Tools 2026/MSVC
19.51. The project uses ordinary C++20/MSVC and CMake features and is expected
to work with the documented minimum, but that exact older toolset remains
unverified in this environment.

## Graphics evidence is hardware-specific

The D3D11 window was interactively verified on one Windows 11 desktop with an
NVIDIA GeForce RTX 3070 Ti. Other adapters, drivers, remote sessions, headless
hosts, and non-D3D11 backends are not claimed as tested. The graphical tests
remain deliberately excluded from default pytest and CTest runs.

## First configure requires network access

Pinned dependencies are fetched from their upstream Git repositories during a
clean first configure/editable install. Subsequent builds can reuse the local
FetchContent checkout, but fully offline clean setup is not yet provided.

## Graphics-disabled builds do not decode texture pixels

The standard Windows client build supports the validated PNG/JPEG path.
`EASY3D_ENABLE_GRAPHICS=OFF` retains asset types and compiles/tests the headless
core without bimg, but `load_image` raises `AssetError` in that configuration.
This keeps future dedicated servers free of image/GPU dependencies. It is not a
client-build limitation; a future headless content validator would require a
separate optional decoder feature.

## Debug bgfx output is verbose

Debug builds emit bgfx capability diagnostics and benign optional-tool notices
for components such as RenderDoc or AMD AGS when those tools are absent. Release
builds provide the concise selected-renderer and adapter log used by the example.

On this machine, Debug D3D11 shutdown also logs an upstream bgfx diagnostic for
the `ID3D11InfoQueue` COM debug interface (`RefCount is 2 (expected 0)`). The
warning is emitted at `renderer_d3d11.cpp:1784`, after Easy3D has queued release
of every mesh/program/uniform handle. Release runs are clean. No formal PIX or
RenderDoc leak capture has been performed yet, so the evidence is deterministic
Easy3D handle teardown and repeated clean process exit rather than a general GPU
driver leak claim.

## Shader artifacts currently target D3D11 only

Easy3D's source shaders are present and reproducibly regenerable with the pinned
bgfx compiler, but only reviewed DXBC Shader Model 5 headers are committed and
runtime-tested. This matches the explicit Windows D3D11 backend. Vulkan,
Direct3D 12, OpenGL, Metal, and WebGPU shader artifacts are not claimed.

## Pinned GLM emits CMake policy deprecation warnings

GLM 1.0.1 is pinned by immutable commit and builds successfully, but its
upstream CMake project requests compatibility with CMake versions older than
3.10. CMake 4.0 therefore emits non-fatal deprecation warnings during a fresh
configure. Easy3D does not suppress or patch vendored warnings; a future reviewed
GLM pin update should re-evaluate them.

