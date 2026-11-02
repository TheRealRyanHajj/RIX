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

Phase 5.4 bandwidth limits apply to replaceable transform frames, not critical
reliable lifecycle/fields/RPC traffic. The default values are engineering
defaults, not a proven 32-player capacity budget. `SpatialInterest` filters
transform updates only: objects remain spawned with reliable fields and hold
their last received pose outside the radius. Deltas are lossy at 1 cm position,
1/16000 quaternion-component and 0.001 scale resolution; larger deltas fall back
to full float32. Transform ACKs are coalesced into bounded unreliable batches
because later ACK state supersedes loss; reliable recovery requests remain
unbatched. Transform updates themselves are still one application message per
object/connection.

The Phase 5.5 arenas are finite headless loopback rule/integration samples.
They do not provide rendered weapons, hitboxes/lag compensation, teams beyond
an integer field, respawn, matchmaking, accounts, persistence, anti-cheat or
Internet hosting. Their 2/4/8-client passes are correctness evidence, not the
32-client capacity workload. Phase 5.6 measures a separate dense all-to-all
headless workload in one process; see `docs/benchmarks.md`. Its aggregate tick
includes all local client polling and does not claim a 60 Hz 32-player game,
external-network quality, rendered-client cost, or dedicated-server-only cost.

The Phase 5.7 soak is finite and local. Its adverse profile uses GNS test-only
process-global fake-send controls, not a measured ISP trace. It verifies
reliable completion under the configured run and application RPC rate limiting;
it does not prove infinite uptime, memory-leak freedom over days, malicious
distributed denial-of-service resistance, authentication, or Internet routing.
Impairment is reset before explicit shutdown so close propagation is tested
deterministically rather than through an arbitrary peer-timeout code.

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

Phase 6.1 graphics are intentionally bounded. The material shader is a compact
direct-light metallic/roughness approximation without environment maps or glTF
material texture channels. Shadows use only the first enabled directional
light, one camera-centered orthographic map and fixed bias; there are no
cascades, point/spot shadows, skinned casters or alpha-cutout casters. Large
outdoor scenes can therefore show missing distant shadows or bias artifacts.

Postprocessing requires RGBA16F plus D24S8 render-target support. Directional
shadows require R32F plus D24S8 and a maximum texture size of at least 2048 or
4096 for the requested preset. Unsupported features fall back and are reported
through `Game.renderer_stats`; a preset name is not proof that every requested
feature is active. Only the D3D11 path on the recorded NVIDIA adapter has been
visually exercised. Other bgfx backends remain unverified.

Easy3D's source shaders are present and reproducibly regenerable with the pinned
bgfx compiler, but only reviewed DXBC Shader Model 5 headers are committed and
runtime-tested. This matches the explicit Windows D3D11 backend. Vulkan,
Direct3D 12, OpenGL, Metal, and WebGPU shader artifacts are not claimed.

## HUD text and layout are deliberately basic

The built-in Roboto atlas contains printable ASCII only; unsupported Unicode
code points display as `?`. There is no font-file API, shaping, kerning, bidi,
fallback font, rich text, clipping/scroll view, rotated UI, nine-slice sprite,
automatic wrapping, retained nested layout, accessibility tree, or keyboard/
gamepad focus navigation yet. A `Stack` must be explicitly relaid out after a
child size changes. Very large labels can exhaust bgfx's transient vertex
buffer for that frame and be skipped rather than overflowing memory.

HUD units are framebuffer pixels. This keeps rendering and hit testing aligned
on high-DPI Windows displays, but does not provide DPI-independent sizing; a
future UI scale policy is required for consistent physical size across mixed-
DPI monitors. Button callbacks are polled in the Python frame bridge and are
not available to a graphics-disabled dedicated server loop.

## Audio is buffered PCM playback, not a full sound engine

Phase 6.3 accepts only uncompressed 16-bit mono/stereo WAV files and decodes the
whole asset into memory. There is no Ogg/MP3/FLAC codec, streaming music,
hot-unload API, device selection/hot-switch policy, bus/effect graph, fades,
pitch control, doppler, HRTF, occlusion, reverb or sample-accurate scheduling.
Spatialization is intentionally basic linear distance rolloff and stereo pan;
it is not a binaural or physically modeled result. Each game retains at most
256 decoded sounds and 1,024 simultaneous voices.

Automated tests verify mixer samples and this Windows host opened its SDL3
default playback stream during a timed D3D11 run. The agent cannot perceive
speaker output, so audible quality and the user's particular endpoint remain a
manual headphone/speaker check with `python examples/10_audio/main.py`.

## Pinned GLM emits CMake policy deprecation warnings

GLM 1.0.1 is pinned by immutable commit and builds successfully, but its
upstream CMake project requests compatibility with CMake versions older than
3.10. CMake 4.0 therefore emits non-fatal deprecation warnings during a fresh
configure. Easy3D does not suppress or patch vendored warnings; a future reviewed
GLM pin update should re-evaluate them.

## glTF rendering is base-pose only

The glTF/GLB importer exposes validated skeletons, clips and native local-pose
sampling, but the renderer does not yet upload joint palettes or deform skinned
vertices. It renders scene-transformed base-pose geometry. Morph targets,
CUBICSPLINE interpolation, multiple skins, matrix-authored joint transforms and
required extensions are rejected rather than approximated. Embedded material
images and alpha modes are not rendered; use external PNG/JPEG base-color maps
and opaque materials for the supported path. The importer currently accepts one
skin with at most 256 joints and local relative buffer/image paths or data URIs,
not network resources.

## Windows editable builds require an MSVC developer environment

If `C:\mingw64\bin` precedes Visual Studio on `PATH`, a plain PowerShell
`pip install -e '.[dev]'` can make CMake select MinGW. That toolchain is not
supported and protobuf 29.3 fails its required tail-call compilation. Run setup
from Visual Studio's x64 Developer PowerShell/Command Prompt and confirm
`cl.exe` is discoverable before invoking pip. The documented MSVC path succeeds;
the project does not modify global `PATH` or silently substitute compilers.

