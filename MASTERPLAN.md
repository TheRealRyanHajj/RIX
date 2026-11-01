# Easy3D — Master Implementation Plan

**Status:** Approved architecture / not yet implemented  
**Version:** 1.0 — 2026-11-01  
**Primary target:** Windows 10/11 x64, Python 3.11+  
**Distribution:** Private repository and private package initially  
**Rule:** This document is the source of truth for scope, ordering, acceptance criteria, and implementation contracts. Update it as implementation proceeds.

## 0. Mission and non-negotiable goals

Build **Easy3D**, a code-first 3D game framework with a friendly Python API and a performant C++20 engine. A beginner should be able to create a textured world, load `.obj` models, place objects, control a player, use physics and state machines, and ultimately host or join multiplayer games with little boilerplate. Advanced users may access lower-level concepts without forcing complexity on beginners.

- **Python-first gameplay:** user-authored game behavior is normal Python classes, methods and optional decorators; no game developer C++ required.
- **Native core:** renderer, physics, entity/component storage, asset cache, network transport, synchronization, and hot-path batch operations are C++.
- **Multiplayer first in the architecture, later in implementation:** cooperative and competitive, authoritative server, listen server, dedicated headless server, target **8–32 players**; no claim that every game will sustain 32 players.
- **Performance first, measurable:** optimize CPU/GPU frame times and 1% lows, not just peak FPS. Native rendering and physics must not need per-entity Python calls each render frame.
- **3D first:** basic 2D sprites/text/HUD later, not a full 2D engine at initial launch.
- **Windows first:** Windows x64 developer/client and Windows headless server are required for first release. Design portability seams; Linux/macOS are **not** first-release deliverables.
- **Local networking first:** direct IP and LAN discovery; room codes, matchmaking, internet NAT traversal, and hosted relays are explicitly deferred.
- **Private initially:** do not publish to PyPI or open-source the repository without explicit approval. Record third-party licenses/notices; private does not remove license compliance obligations.
- **Do not mark an item complete without tests and runnable proof.** Never claim benchmark results not actually measured.

### Locked technology decisions

| System | Choice | Implementation note |
|---|---|---|
| Core | C++20 | MSVC/Visual Studio 2022 toolchain; x64 |
| Python | CPython 3.11+ | Initially validate 3.11 on Windows; add/version-test newer CPython releases explicitly |
| C++ ↔ Python | pybind11 | Native extension `_easy3d`; high-level `easy3d` Python package |
| Packaging | CMake + scikit-build-core | Editable development install and locally built wheel |
| Window/input | SDL3 | Avoid depending on Pygame in engine runtime |
| Graphics | bgfx | Default Windows D3D11 if stable; automatic/fallback options; never assume Vulkan |
| Physics | Jolt Physics | Fixed tick, rigid bodies, collision queries, character motor |
| Networking | GameNetworkingSockets | Transport only; custom replication and authority above it |
| Mathematics | GLM internally | Public `Vec2`, `Vec3`, `Quat` wrappers; consistent conversions |
| Mesh imports | tinyobjloader first | glTF/GLB importer later; model caching |
| Textures | stb_image or equivalent | PNG/JPEG initial support, color space semantics |
| Tests | CTest + pytest | Unit, integration, end-to-end, load, soak |
| Dependencies | vcpkg manifest or pinned CMake integration | Lock tested revisions; never float main branch in reproducible builds |

**Dependency reality check:** bgfx is a renderer, not a scene engine; we own materials, passes, culling, and resource management. GameNetworkingSockets is a transport, not a replication framework. Its Windows build requires careful integration of Protobuf and crypto dependencies. Jolt does not make arbitrary Python game logic deterministic.

## 1. Product contract: simple API without hidden magic

### 1.1 Minimal game (desired eventual API)

```python
from easy3d import Game, Scene, Plane, Cube, Player, Light

game = Game(title="First World", resolution=(1280, 720), physics_hz=60)
world = Scene("main")
with world:
    Plane(size=(100, 100), texture="assets/grass.png", collider=True)
    Cube(position=(0, 1, 5), texture="assets/stone.png", collider=True)
    Player(position=(0, 3, 0), controller="first_person")
    Light(type="directional", rotation=(45, -30, 0))
game.load_scene(world)
game.run()
```

This is the **target contract**, not Phase 0 scope. Examples must not be labeled working until they run in CI.

### 1.2 API organization

- `easy3d`: convenience re-exports: `Game`, `Scene`, `Entity`, `Cube`, `Plane`, `Sphere`, `Model`, `Player`, `Camera`, `Light`, `Vec2`, `Vec3`, `Quat`.
- `easy3d.components`: `Transform`, `MeshRenderer`, `Collider`, `Rigidbody`, `CharacterController`, `NetworkIdentity`, `NetworkTransform`, `AudioSource` (when implemented).
- `easy3d.physics`: casts, overlaps, constraints, collision events and layers.
- `easy3d.network`: `Server`, `Client`, `NetworkVar`, `rpc`, `network.spawn`, network statistics, ownership/authority.
- `easy3d.input`: `Input`, action maps, mouse and controller input.
- `easy3d.logic`: `StateMachine`, `Timer`, `Cooldown`, `EventBus`, `Tween`.
- `easy3d.assets`: asset handles, paths, cache and asynchronous loading (later).
- `easy3d.debug`: logging, profiling, collision overlays, engine stats.
- `_easy3d`: private native extension. Python users must not need to import it directly.

### 1.3 Entity and component data model

- Native entity registry is authoritative for entity lifetime and native component state. Entity references are **generation-checked handles**, scoped to a world/scene, not bare memory pointers. Invalid access raises a documented Python `ReferenceError`/engine-specific exception rather than crashing.
- `Entity` is a Python wrapper, with optional Python gameplay behavior. Primitive classes are convenience constructors over `Entity + MeshRenderer + [Collider]` and may be subclassed.
- Each entity has `id`, `name`, `enabled`, `visible`, `scene`, `parent`, `position`, `rotation`, `scale`; scene ownership is explicit or acquired from `with scene:`. No unqualified global default world.
- Coordinate standard: **right-handed**, **+Y up**, **camera forward -Z**, **meters**, **degrees for public Euler angles**, **quaternion native rotation**. Specify UV orientation and front-face winding in renderer tests.
- `Vec3` supports properties `.x/.y/.z`, construction from a tuple, arithmetic, equality with explicit float limitations, and conversions. `entity.position.x += 1` must persist to native state (either a live proxy or a setter-backed vector), not modify a detached temporary.
- `Transform` supports local/world space, parenting with keep-world flag, cycle rejection, and dirty propagation. Physics-owned dynamic transforms update under documented precedence; scripts cannot silently overwrite dynamic bodies every render frame.
- Components have defined singleton-vs-multiple rules; `add_component`, `get_component`, `remove_component`; native ownership vs Python behavior ownership documented; entity deletion is deferred safely within callbacks.
- Assets use reference-counted native handles and shared mesh/texture resources, with deterministic cache keys and clean GPU release.
- `Model("x.obj", ...)` supports positions, normals, UVs and material/texture assignment; collider `"mesh"` means static triangle-mesh collider unless explicitly documented otherwise. Dynamic rigid bodies default to convex/compound shapes, not arbitrary moving triangle mesh.

### 1.4 Scripts and lifecycle (ordered contract)

```python
class Enemy(Entity):
    def awake(self): ...
    def start(self): ...
    def fixed_update(self, dt): ...
    def on_collision_enter(self, other): ...
    def update(self, dt): ...
    def late_update(self, dt): ...
    def on_destroy(self): ...
```

- Construction/registration occurs before `awake` (once); `start` once on first activation; disabled entities do not receive active ticks; re-enabling does not rerun `start`.
- Each **simulation tick**: drain verified input/network commands -> apply scheduled spawn/despawn at safe boundary -> Python `fixed_update(dt)` on eligible server/offline scripts -> native physics step -> enqueue/dispatch collision callbacks -> commit authoritative state and build replication snapshots. The exact collision timing is documented by tests.
- Each **client render frame**: interpolate visuals -> Python `update(dt)` -> Python `late_update(dt)` -> renderer submission/present. Render-frame callbacks are not run on headless servers. A listen-server may have distinct server/client contexts in one process; no accidental double execution.
- Clamp frame delta and cap fixed catch-up ticks to prevent spiral-of-death; expose overruns and time dropped/skipped. Default physics tick 60 Hz. Timers explicitly choose wall time, render time or simulation tick time.
- Python callbacks execute on a designated simulation/gameplay thread with GIL acquired. C++ jobs do not call Python from uncontrolled threads. Worker queues have cancellation and shutdown rules.
- Exception handling: log stack trace and entity identity, configurable fail-fast in development; don't corrupt the engine or silently swallow errors.
- `StateMachine` supports enter/update/exit, transition validation, time accounting, reentrancy guards, event-driven transitions; independent of graphics. `@state` decorators optional.
- Python scripting is **not** assumed deterministic, and not every Python movement script is automatically eligible for network prediction.

### 1.5 Rendering contract

- bgfx backends abstracted behind `Renderer`; no raw bgfx resources leak into beginner API.
- Initially: clear screen, indexed mesh, transform, camera, depth test, solid-color material, textured material, point/directional light baseline, resized window, VSync toggle, screenshot/debug counters.
- Extend: mesh import, frustum culling, static batching and/or GPU instancing, transparent pass, material texture caching, shader variants, quality presets, optional shadows, optional postprocessing/AA, optional PBR.
- Frame rate unlocked by `fps_limit=0`; independent simulation tick. Configurable VSync; sensible safety cap for idle/unfocused windows.
- Diagnostics: FPS and frame time distributions, CPU/GPU timings where backend supports, draw calls, triangles, entities, texture/mesh memory, Python callback cost. No fabricated performance guarantees.
- Quality presets low/medium/high/custom, balanced performance-first defaults. Render features are gated by backend capability checks and graceful fallbacks.

### 1.6 Physics contract

- Jolt integrated into per-world physics state; supported body types static, dynamic, kinematic, trigger/sensor, and character-controller abstraction.
- Shapes: box, sphere, capsule, convex and static triangle mesh; compound later. Explicit collision layers/masks, friction, restitution, mass, sleeping, continuous collision detection option.
- Queries: raycast, sphere/capsule cast, overlap box/sphere; query filters and sorted/unsorted result semantics documented.
- Force/impulse and constraints/joints; physical units and timestep behavior documented; collision enter/stay/exit and trigger counterparts.
- Jolt must not be accessed concurrently while stepping unless supported by its API. Python callbacks get safe snapshots/results. Headless physics runs without GPU initialization.
- Native first-person/third-person `CharacterController` handles grounded state, slope/step behavior, jump, collision/sliding. Python controls speed, acceleration, camera behavior and events.

## 2. Multiplayer design contract

### 2.1 Modes, transport and authority

- Modes: offline single-player; **listen server** (local authoritative server and client with isolated roles); **dedicated headless server**; remote client. Same game rules should be reused as much as reasonable.
- Multiplayer supports **co-op and competitive** play. Target capacity **8–32 players**, validated against a documented sample workload, not arbitrary games.
- Network transport: GameNetworkingSockets over UDP (reliable/unreliable channels, encrypted transport). Network payloads are bounded binary schemas, **never** Python `pickle` or arbitrary code.
- First connectivity: explicit IPv4/IPv6 address + port where feasible, plus LAN discovery; direct internet joins need appropriate routing/firewall configuration. **No promise of automatic NAT traversal or relay support.** Default example port is 7777/UDP, configurable.
- Server authoritative for game rules, health, inventory, scoring, damage, spawning, and gameplay physics. Clients send inputs/requests, not authoritative outcomes. No built-in guarantee against all cheating.
- Logical roles `offline`, `server`, `client`, `listen_server` and script execution contexts `server`, `client`, `shared`, optionally `predicted` only for supported movement modules.

### 2.2 Identity, replication and ownership

- Native entity handle != network entity identity. Server-assigned `network_id` with lifecycle generation/epoch, owner connection ID, prefab/type ID, spawn tick and replication schema version. Never assume stable entity memory addresses across hosts.
- Typed `NetworkVar` descriptors: `bool`, bounded integer, float, Vec2/Vec3, quaternion, bounded UTF-8 strings, enums, small bounded arrays/maps (later). Declare type, default, authority, replication policy, optional on-change callback. No arbitrary object graph serialization.
- Replicate: network spawn/despawn, ownership changes, relevant component state. Initial snapshot/late join must establish authoritative state before delivering deltas. Missing baselines cause explicit resync, not silent corruption.
- Snapshot frequency starts at 20 Hz, server tick at 60 Hz; values configurable. Entity/field dirty tracking and sequence/ack conventions; bandwidth counters and packet limits.
- Interest management: initial all-relevant room/world for 8–32 test; spatial relevance and priority scheduling before production scale claim.
- Entity creation uses **registered prefabs**, not importing arbitrary client-selected Python classes. Ownership and network visibility checks enforced.

### 2.3 RPC contract

```python
from easy3d.network import rpc, NetworkVar

class Weapon(Entity):
    ammo = NetworkVar(int, default=30, authority="server")

    @rpc(target="server", reliable=True, rate_limit=10)
    def request_fire(self, direction: Vec3):
        # Executed on server after ownership, schema and rate checks.
        ...
```

- RPCs explicitly registered at startup; stable IDs/versioning; allowed directions client→server and server→client(s). Validate sender, ownership, argument type/size, scene and game conditions; use per-RPC rate limits.
- Reliable ordered channel for critical events; replaceable snapshots prefer unreliable sequencing. No gameplay authority transferred simply because a message arrives reliably.
- Do not re-execute critical non-idempotent actions on retries without deduplication where needed.

### 2.4 Movement, synchronization and robustness

- Stage 1: remote transform interpolation; local input transported to server and authoritative position replicated.
- Stage 2: native character motor with input sequence numbers, client prediction, server reconciliation and bounded replay; interpolation of other players. Custom arbitrary Python behavior remains non-predicted unless opted into a defined deterministic contract.
- Snapshot buffer default 100ms (tunable). Include RTT, jitter, loss, server tick drift, bandwidth stats.
- Handle disconnect/reconnect policy, failed handshakes, version mismatch, bounded connection queues, host shutdown, timeout and malformed packets.
- Authentication extension hooks; no built-in public account backend. Do not imply UDP transport encryption alone authenticates game identities.
- LAN discovery uses bounded UDP broadcast/multicast approach as appropriate, with explicit user opt-in and safe parsing; direct IP remains functional without discovery.
- Test both authoritative remote clients and listen-server host behavior to catch host advantage / double-simulation bugs.

### 2.5 Multiplayer API targets

```python
# server.py (eventual)
from easy3d.network import Server
server = Server(port=7777, max_players=32, tick_rate=60, headless=True)
server.load_scene("arena")
server.run()

# client.py (eventual)
from easy3d import Game
game = Game(title="Arena")
game.connect("192.168.1.50", port=7777)
game.run()
```

API must include on_connect/on_disconnect, protocol errors, player ownership, registration of network prefabs, explicit network spawning/despawning, and stats. Code examples become CI fixtures when implemented.

## 3. Repository and tooling layout

```text
easy3d/
├─ MASTERPLAN.md                 # copy of this plan in repository
├─ README.md
├─ pyproject.toml
├─ CMakeLists.txt
├─ CMakePresets.json
├─ vcpkg.json                    # only if chosen dependency strategy
├─ LICENSES/                     # third-party notices, private project
├─ cmake/
├─ engine/
│  ├─ include/easy3d/           # stable internal/native public headers
│  └─ src/
│     ├─ core/                  # Game, tick clock, scheduler, logging
│     ├─ scene/                 # registry, handles, components, transforms
│     ├─ renderer/              # bgfx adapter, meshes, materials, views
│     ├─ assets/                # importers, resource caches
│     ├─ input/                 # SDL3 events, action maps
│     ├─ physics/               # Jolt world and queries
│     ├─ network/               # transport, replication, RPC, interest
│     └─ platform/              # window, filesystem
├─ bindings/
│  └─ module.cpp                # pybind11, split as features grow
├─ python/easy3d/
│  ├─ __init__.py
│  ├─ _version.py
│  ├─ game.py
│  ├─ scene.py
│  ├─ entity.py
│  ├─ components.py
│  ├─ input.py
│  ├─ logic.py
│  ├─ physics.py
│  ├─ network.py
│  ├─ assets.py
│  ├─ debug.py
│  └─ py.typed
├─ examples/
│  ├─ 00_window/
│  ├─ 01_triangle/
│  ├─ 02_first_world/
│  ├─ 03_character_physics/
│  ├─ 04_state_machine/
│  ├─ 05_multiplayer_lan/
│  └─ 06_multiplayer_arena/
├─ tests/
│  ├─ cpp/
│  ├─ python/
│  ├─ integration/
│  └─ performance/
├─ docs/
│  ├─ architecture.md
│  ├─ api-contract.md
│  ├─ threading-lifecycle.md
│  ├─ network-protocol.md
│  ├─ benchmarks.md
│  └─ decisions.md              # ADRs and design changes
└─ .github/workflows/            # private CI
```

Use **one canonical spelling**: repository `easy3d`, import `easy3d`, native module `easy3d._easy3d`. User-facing package name may change if availability conflicts arise; don't rename internal symbols mid-phase without migration notes.

## 4. Phased execution checklist

**Working rule for every step:** implement smallest testable slice; write/update tests and docs; execute builds/tests; log proof and blockers; mark **DONE** only if acceptance criteria pass. If environment prevents testing, mark **BLOCKED/UNVERIFIED**, not DONE. Keep all phases in order except isolated documentation work. Don't request human confirmation for routine technical details; record defaults/ADRs.

### PHASE 0 — Reproducible native foundation (must be done first)

- [x] **0.1** Inventory repository and local environment (OS, VS2022/MSVC, CMake, Ninja, Python 3.11, Git). Preserve existing work. Record versions and missing prerequisites.
- [x] **0.2** Bootstrap layout, `.gitignore`, README, this masterplan, `docs/decisions.md`, formatting/lint rules and private-project notices.
- [x] **0.3** Implement modern CMake project with an `easy3d_core` C++20 library target, strict compiler warnings, Debug/Release configurations, and CTest smoke test.
- [x] **0.4** Implement Python `pyproject.toml` using scikit-build-core and pybind11, building `easy3d._easy3d`. Install via `python -m pip install -e .` and verify import in Windows Python 3.11.
- [x] **0.5** Bind `engine_version()`, `native_add(a,b)`, an exception translator, and a minimal native `Engine` instance. Verify native and Python tests.
- [x] **0.6** Integrate SDL3 and create/close a resizable native Windows window with clean quit flow; input polling and monotonic frame clock.
- [x] **0.7** Integrate bgfx as pinned dependency; render/clear frames through D3D11 on Windows. Ensure correct native window handle, resize/reset, init/shutdown order. Log selected backend and adapter.
- [x] **0.8** Provide Python `Game(title, resolution, ...)` and `game.run()` / `game.stop()` API to display the blank window. On failure raise meaningful Python exception; repeated open/close must not crash.
- [x] **0.9** Add automated non-GPU unit test and an explicit manual/interactive smoke-test command for Windows GPU window. Ensure CI doesn't falsely claim graphical tests ran in a headless runner.
- [x] **0.10** Add basic benchmark harness, timings, build/run instructions, third-party dependency pins and known issues.

**Phase 0 exit gate:** `python -m pip install -e .`; `python -c "import easy3d; print(easy3d.engine_version())"`; `pytest`; `ctest`; and `python examples/00_window/main.py` (interactive on Windows) work. `Game.run()` opens a native window, renders blank frames, handles resize and exits cleanly. Record exact commands/results; no OpenGL/Pygame scripting required.

**First delivery checkpoint:** Stop to report when this gate passes or when a genuine blocker is documented. Do not begin networking before Phase 0 is stable.

### PHASE 1 — Scene, entities, transforms, rendering, assets

- [x] **1.1** Define `World`, `Scene`, entity handle semantics and ownership/lifetime API; add create/destroy/reuse tests.
- [x] **1.2** Implement `Vec2`, `Vec3`, quaternion and Euler facade, transforms, parenting and dirty propagation; test local/global transform correctness.
- [x] **1.3** Create mesh/material abstractions and GPU buffer lifetime manager; render triangle, cube, plane, sphere with depth testing.
- [x] **1.4** Build camera/view/projection, configurable near/far planes, aspect ratio and resize handling.
- [x] **1.5** Build shared texture loading/caching (PNG/JPEG, UVs, sampler settings, sRGB); missing asset errors.
- [x] **1.6** Build `.obj` loader with normals/UV/material support where practical and explicit documented limitations; share mesh resources across instances.
- [x] **1.7** Implement primitive entities (`Cube`, `Plane`, `Sphere`, `Model`), `Entity` property API and component lookup.
- [x] **1.8** Implement directional/ambient lighting baseline, basic materials and debug rendering.
- [x] **1.9** Add frustum culling, simple instancing or batching, renderer counters, and benchmark scenes.
- [x] **1.10** Run `examples/02_first_world`, test 10k static cubes with shared resources, record FPS distributions and memory with actual device specs.

**Exit gate:** first-world example displays textured assets, moving camera, clean scene teardown; bounds and transforms tested; no unchecked stale handles or resource leaks observed in repeated loading tests.

### PHASE 2 — Python gameplay, utilities, complete physics foundation

- [x] **2.1** Implement input mapping (keyboard/mouse/gamepad), pointer lock, focus behavior, remappable actions.
- [x] **2.2** Implement script lifecycle and simulation scheduler, error propagation, deferred mutation and profile callback times.
- [x] **2.3** Build standalone `StateMachine`, `Timer`, `Cooldown`, `EventBus`, `Tween` with tests independent of graphics.
- [x] **2.4** Integrate Jolt world, collision layers, gravity, body lifetime and fixed stepping; test headless without renderer.
- [x] **2.5** Expose basic colliders and rigid bodies, impulses/forces, physical materials, triggers; validate conversions and safety.
- [x] **2.6** Expose physics queries and event callbacks; verify collision enter/stay/exit and trigger transitions.
- [x] **2.7** Build first-person and third-person native character motors with Python configuration hooks; movement, slope, jump and grounded detection.
- [x] **2.8** Implement advanced shapes/constraints and CCD, in priority order after basic correctness.
- [x] **2.9** Deliver playable single-player obstacle-course example and physics regression suites.

**Exit gate:** Python game defines classes with `fixed_update`, player moves/jumps on physics terrain, objects collide and fall, collision callbacks work, headless Jolt tests pass, simulation tick independent of rendering FPS.

### PHASE 3 — Transport, roles, headless server

- [x] **3.1** Create platform-neutral `NetworkTransport` interface, connection IDs, bounded message queues and simulated loss/latency tests.
- [ ] **3.2** Integrate pinned GameNetworkingSockets Windows build and its tested Protobuf/crypto dependencies; use appropriate vcpkg/CMake wiring; license/audit docs.
- [ ] **3.3** Implement protocol handshake: version/schema compatibility, limits, client/server role identification, disconnect reasons.
- [ ] **3.4** Implement client connect/disconnect, IP/port, timeouts, error handling, callbacks, network metrics.
- [ ] **3.5** Implement headless `Server` running simulation and Python server logic without SDL window or bgfx device.
- [ ] **3.6** Implement listen server with isolated authoritative and client roles and no duplicated authority callbacks.
- [ ] **3.7** Implement LAN discovery as opt-in, bounded and robust; document Windows firewall/local subnet behavior.
- [ ] **3.8** Two-process LAN/local loopback sample, automated server/client integration tests, abrupt disconnect/port collision tests.

**Exit gate:** headless server starts without graphics; client connects over loopback/direct IP and exchanges bounded messages; protocol mismatch and disconnect are recoverable; no entity synchronization claims yet.

### PHASE 4 — Replication, networked gameplay

- [ ] **4.1** Implement stable network IDs, prefab registration, schema/version mapping, server-owned spawn/despawn and late join.
- [ ] **4.2** Implement typed `NetworkVar`, dirty tracking, serialization bounds and authority checks.
- [ ] **4.3** Implement `NetworkTransform`, snapshot tick/sequence, interpolation for remote actors and basic relevance filtering.
- [ ] **4.4** Implement RPC registration, direction/ownership authorization, rate limiting, reliable/unreliable channels and defensive parsing.
- [ ] **4.5** Implement game-context/script-authority guards; prevent double execution on listen hosts.
- [ ] **4.6** Implement replicated match states and server-only timers; late-join state correctness.
- [ ] **4.7** Build 2–8 player co-op sandbox sample: objects spawned, moved, hit, destroyed, synchronized.
- [ ] **4.8** Add integration tests for malicious/invalid RPC, ownership tampering, out-of-order updates, state resync, join/leave.

**Exit gate:** networked entity lifecycle and gameplay values remain coherent across clients; client cannot modify server-only fields by sending unauthorized messages.

### PHASE 5 — Responsive 8–32 player multiplayer

- [ ] **5.1** Implement input-sequenced native predicted character motor on client and server.
- [ ] **5.2** Implement server reconciliation and bounded replay, remote interpolation and correction telemetry.
- [ ] **5.3** Add lag/jitter/loss simulator and test at representative network conditions; document failure behavior.
- [ ] **5.4** Implement bandwidth budgets, entity prioritization, spatial interest and delta-baseline recovery.
- [ ] **5.5** Build cooperative and competitive arena samples with authoritative damage/scoring and match states.
- [ ] **5.6** Build bots/simulated clients for 8, 16, 32 connections; measure tick cost, CPU/RAM, bandwidth, latency, correctness; optimize measured bottlenecks.
- [ ] **5.7** Soak test reconnects/disconnects, input spam, packet loss and server shutdown.

**Exit gate:** documented sample workload with 32 simulated connections operates within declared CPU/memory/bandwidth budgets on a recorded test machine; no unsupported performance claims. Client prediction and authority demonstrate clear behavior under latency.

### PHASE 6 — Graphics polish, 2D HUD, usability, packaging

- [ ] **6.1** Add optional lighting upgrades, shadows, PBR/material variants, postprocessing and AA with capability fallbacks and presets.
- [ ] **6.2** Add basic 2D sprites, text, HUD, anchoring/layout and clickable buttons; support overlays above 3D.
- [ ] **6.3** Add audio playback and basic positional audio (choose a lightweight backend through an ADR).
- [ ] **6.4** Introduce glTF/GLB loader, animation skeleton and animation clips once import needs are defined.
- [ ] **6.5** Add asset error diagnostics, debug overlays, documentation, annotated API examples and type-stub/type-checking coverage.
- [ ] **6.6** Produce Windows Python 3.11+ wheel matrix only for interpreters actually tested; verify install from wheel on clean environment.
- [ ] **6.7** Establish versioning, compatibility policy, migration notes and private artifact distribution instructions.
- [ ] **6.8** Run full regression, soak, packaging and performance tests; record performance before/after optimizations.

**Exit gate:** a new developer can install from a private wheel, follow a quickstart, build a simple 3D game and a local multiplayer example, with no native compilation required on their machine.

## 5. Measurable quality gates and test plan

- **Build quality:** clean Windows x64 Debug + Release builds; CTest native suite; pytest Python suite; no unsuppressed critical sanitizer/static-analysis issues where tools are available.
- **Correctness:** stale handles, parenting cycles, zero-length vectors, missing textures, malformed OBJ, invalid collider types and Python exceptions handled safely.
- **Timing:** fixed-step determinism of scheduler ordering (not arbitrary world replay determinism), capped catch-up steps and correct pause behavior.
- **Resource management:** repeated window/scene setup and teardown and headless server start/stop do not crash; memory and GPU resource counts return close to baseline.
- **Performance:** track median/95th/99th frame/tick durations, 1% low FPS, draw calls, allocations, memory and network bytes per second; annotate hardware, drivers, resolution and workload. Set meaningful pass/fail budgets after first benchmark baseline, not guessed thresholds.
- **Multiplayer:** protocol fuzz/invalid payload tests, client/server version mismatch, connection loss, unauthorized RPC, late join and ownership changes; loopback and LAN manual verification.
- **Packaging:** clean Python venv import, missing DLL detection, proper dependency bundling, version reporting and full editable-install reproduction from README.
- **Docs:** each phase includes an example, public API docs, limitations, exact test commands and evidence in progress log.

## 6. Out-of-scope until explicitly approved

- Visual scene editor / drag-and-drop authoring; Unity-like tooling.
- Built-in internet matchmaking, accounts, lobby backend, hosted dedicated server fleet, relay infrastructure or automatic NAT traversal.
- Linux and macOS binaries in first release (keep abstractions portable).
- Full 2D engine parity or browser/mobile/console targets.
- World streaming/MMO architecture or promise of 100+ players.
- Arbitrary untrusted Python code downloaded and executed from multiplayer peers.
- Fully deterministic replays of all possible Python game scripts.
- Premature custom shader language, custom networking transport or custom rigid-body solver.

## 7. Agent working protocol (Codex)

1. Read `MASTERPLAN.md` before modifying code. Inspect existing repository and `git status` first; avoid overwriting prior implementation or secrets.
2. Identify the first unchecked item in the earliest incomplete phase. Work on a **bounded, independently testable** vertical slice.
3. Before editing, write a short approach in the work log with files affected, risks and test commands.
4. Implement real, runnable code; prefer pinned dependencies, clear ownership and narrow interfaces. Do not add empty placeholder modules merely to claim milestones.
5. Run the tests appropriate to your change; record **exact commands, results and environment**. Distinguish automated tests from manual interactive checks. If Windows hardware is unavailable, mark Windows-only checks unverified and prepare reproducible commands.
6. Keep `docs/decisions.md`, `docs/progress.md` and `MASTERPLAN.md` checkboxes up to date. Each completed item records a short proof reference (test, example or benchmark).
7. Fix regressions before moving on. Never delete tests to make a build green or silently weaken acceptance criteria.
8. On dependency/build blockers, retry reasonably, then document root cause and an actionable reproducible next step; continue only with unrelated safe work. Don't fabricate successful builds.
9. Commit cohesive changes if repository permissions allow; don't push, publish, deploy, alter private visibility or install global system packages without approval.
10. **Initial handoff scope is Phase 0 only.** Finish Phase 0, provide its evidence, known limitations and next step. Later phases require a new user/agent instruction even though this masterplan contains all milestones.

## 8. First-run setup commands (Windows PowerShell)

These are **targets after bootstrapping**. Prerequisites: Visual Studio 2022 Build Tools with Desktop development with C++, Python 3.11, Git, CMake/Ninja; pin library dependencies before build.

```powershell
# From repository root in a suitable VS2022 developer environment
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -c "import easy3d; print(easy3d.engine_version())"
python -m pytest -q
cmake --preset windows-debug
cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
python examples/00_window/main.py
```

The agent must create compatible presets/extras, check tool availability, and adjust documented commands if dependency install requirements dictate another order. An interactive GPU window test must run on an actual Windows desktop session; headless CI should not claim it passed.

## 9. Definition of done for the whole project

A Python developer can install a prebuilt private Windows package, create a textured 3D scene with primitives and OBJ models, implement gameplay classes, use colliders and rigid bodies, drive a first-person controller, use state machines/events, and run a co-op/competitive multiplayer example with up to 32 simulated connections on a documented test machine. Both headless server and host-and-play modes pass integration tests. Performance and limitations are measured and documented, and no user C++ code is necessary for ordinary gameplay.

## 10. References to verify and pin during implementation

- bgfx: https://github.com/bkaradzic/bgfx ; renderer/platform documentation: https://bkaradzic.github.io/bgfx/
- SDL3: https://wiki.libsdl.org/SDL3/FrontPage
- Jolt Physics: https://github.com/jrouwe/JoltPhysics
- GameNetworkingSockets build guidance: https://github.com/ValveSoftware/GameNetworkingSockets/blob/master/BUILDING.md
- pybind11: https://pybind11.readthedocs.io/
- scikit-build-core: https://scikit-build-core.readthedocs.io/
- GLM: https://github.com/g-truc/glm

**Revision policy:** architectural changes require an ADR explaining consequences for API, tests, multiplayer and compatibility. Never convert a future goal into a claim of implemented functionality without evidence.
