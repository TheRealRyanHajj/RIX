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

Phase 3.5 exposes a numeric direct-IP client and headless authoritative server
with the Phase 3.3 handshake. There is not yet a listen-host role, DNS, LAN
discovery, automatic firewall rule, player identity, replication, or supported
two-process sample; those are Phase 3.6–4.x work. Transports advance only when
their owning thread polls (the server `run()` loop does this automatically), so
a stalled owning loop also stalls callbacks and deadline enforcement.
Exact protocol/schema equality is the only compatibility policy in wire format
1; migrations or version ranges are not implied.

Python connect/disconnect callbacks are synchronous `poll()` callbacks. If one
raises, the exception propagates after its event was drained and the callback
is not replayed. GNS rate/ping metrics can be zero or `-1` before enough live
traffic exists. Direct transport encryption is unauthenticated and is not a
player/account identity guarantee.

Server bind addresses are numeric only. Binding a LAN-facing address can cause
Windows Firewall to prompt or block inbound traffic; Easy3D does not create or
modify firewall rules. Phase 3.5 is validated over local IPv4 loopback, with
native multi-client and Python client/server tests. Separate-process LAN and
abrupt-process-loss validation remain Phase 3.8.

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

