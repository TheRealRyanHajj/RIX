# RIX — Engine, Multiplayer, and State Systems Master Plan

## Mission

Build a small, maintainable, Windows-first 3D game framework with a friendly
typed Python API and a performant C++20 core. A beginner should be able to make
a playable single-player or multiplayer game without learning engine internals, while an
advanced user can opt into explicit scenes, entities, components, physics,
rendering, assets, audio, UI, diagnostics, scheduling, networking, replication,
and authoritative servers.

Networking is an optional subsystem. Pygame-only messaging and headless servers
must not initialize a window, renderer, physics world, or 3D scene unless the
application explicitly asks for those systems. The 2026-11-06 multiplayer and
state-machine goal supersedes the earlier networking-removal decision.

## Product principles

- Native hot paths: rendering, physics, transforms, asset decoding, audio
  mixing, and batch traversal stay in C++.
- Python owns game rules and approachable composition, not per-object native
  plumbing.
- Explicit lifetime: `Game`, `Scene`, entities, native resources, and callbacks
  have deterministic ownership and idempotent teardown.
- No hidden global world: convenience construction is context-local and the
  explicit `scene=` path always remains available.
- Fixed simulation and rendering have separate clocks.
- Public Python and native handle types are typed and tested.
- Dependencies are pinned, private where practical, and license-audited.
- Claims require automated evidence or clearly labelled interactive evidence.

## Locked technology

| Area | Choice | Boundary |
|---|---|---|
| Language | C++20 + Python 3.11–3.13 | pybind11 boundary |
| Build | CMake + Ninja + scikit-build-core | Editable installs and wheels |
| Window/input/audio | SDL3 | Native Windows lifecycle |
| Rendering | bgfx, D3D11 initially | Easy3D owns scene/material policy |
| Physics | Jolt Physics | Easy3D handles and components |
| Math | Easy3D value types, private GLM | No GLM types in Python |
| Assets | tinyobjloader, cgltf, bimg | Easy3D-owned immutable data |
| Tests | CTest + pytest + mypy | Native, Python, and typing gates |

## Implemented architecture contract

### Game and scheduling

`Game` owns one native engine/window and at most one active `Scene`. It exposes
update, fixed-update, input, timer, renderer, lighting, audio, and clean-shutdown
services. User callbacks run on the gameplay/window thread. Fixed steps are
bounded to avoid a spiral of death.

### Scenes and entities

Scenes own world-scoped generational handles. Stale or cross-world handles are
rejected. Parent/child transforms preserve local/world invariants. Mutations
that would invalidate native traversal are deferred or rejected at documented
boundaries.

### Rendering and assets

The renderer owns GPU resources and consumes native scene snapshots. Cameras,
lights, culling, instancing, shadows, post-processing, debug lines, and retained
2D overlays use explicit limits and observable counters. OBJ, glTF/GLB, PNG,
JPEG, and WAV data are validated and converted into Easy3D-owned forms.

### Input and player movement

SDL events become remappable action/button/axis state. `Player` composes the
native character motor and camera policy. Movement uses normalized wish input,
ground friction, projection-based ground/air acceleration, and edge-triggered
jumps. Correctly timed landing jumps preserve momentum; held jump, coyote time,
and jump buffering are intentionally absent. Sprint, crouch, slopes, and steps
remain ordinary local simulation features; there is no remote-input or
prediction layer.

### Physics

Each scene lazily owns a Jolt world. Rigid bodies, colliders, triggers,
character motors, queries, contacts, constraints, and CCD are exposed through
Easy3D handles. Physics state has documented transform precedence, and Python
callbacks receive immutable event snapshots.

### Python convenience layer

Convenience entities and gameplay/UI helpers compose the same production
systems as explicit components. They must not create parallel engines or hide
resource ownership. Advanced users can always drop down to explicit scenes and
components.

## Current completion checklist

### Foundation

- [x] Reproducible CMake/scikit-build-core project and editable install.
- [x] C++20 core, pybind11 extension, typed public package, exception boundary.
- [x] SDL3 Windows lifecycle and bgfx D3D11 clear/present/resize path.
- [x] Native and Python smoke/unit targets plus documented Windows setup.

### World and rendering

- [x] Generational entities, scenes, transforms, hierarchy, and lifetime tests.
- [x] Meshes, camera, textures, OBJ, glTF/GLB, lights, debug drawing.
- [x] Culling, instancing, renderer counters, presets, shadows, post-processing.
- [x] Retained HUD/UI primitives, layout, text, sprites, and buttons.

### Gameplay and simulation

- [x] Input maps and SDL keyboard/mouse/gamepad translation.
- [x] Update/fixed-update scheduler and standalone gameplay utilities.
- [x] Jolt rigid bodies, colliders, queries, events, characters, constraints,
  advanced shapes, and CCD.
- [x] First-/third-person Player with jump, sprint, crouch, and camera follow.
- [x] Gameplay helpers for health, enemies, combat, teams, scoring, interaction,
  spawn/respawn, timers, events, states, and tweens.
- [x] Native WAV audio and positional sources.

### Developer experience and release

- [x] Beginner examples, focused feature examples, docs, diagnostics, and typing.
- [x] Python 3.11–3.13 Windows wheel matrix and version policy.
- [x] Private dependency notices and immutable pins.
- [x] Rerun editable-install, Python, typing, and Debug native regression after
  the networking removal and record exact evidence in `docs/progress.md`.
- [x] Rerun the complete Python 3.11–3.13 wheel matrix after the networking
  removal.
- [x] Perform a fresh interactive Windows window/input/audio/visual smoke after
  the removal and record the hardware-specific result.

## Quality gates

- `python -m pip install -e '.[dev]'` succeeds in an MSVC developer shell.
- `python -c "import easy3d; print(easy3d.engine_version())"` succeeds.
- All retained pytest and CTest targets pass.
- Strict type-check coverage passes for representative public APIs.
- Wheels for supported Python versions contain the extension, typed package,
  license, and notices without build-only dependency artifacts.
- Interactive evidence is never inferred from headless tests.
- Networking-disabled builds use the bounded stub backend; networking-enabled
  builds pass native transport and independent-process integration gates.

## Phase 10 — Pygame-level Python API simplification

This phase implements the beginner-first API described by the 2026-11-02 API
simplification goal. It is additive: existing explicit scenes, components,
physics queries, audio, UI, assets, and standalone utilities remain supported.

### 10.1 Unified managed and manual loop

- [x] Add `Game.running` and `Game.tick(fps=None)` over the same native frame
  step and Python scheduler used by `Game.run()`.
- [x] Make native window initialization persistent across manual ticks and
  deterministic on `close()`; reject recursive/concurrent loop control.
- [x] Test event/input, callback, fixed-step, render-count, stop, exception,
  frame-limit, context-manager, and repeated-lifecycle semantics.
- [x] Document exact poll/simulate/callback/render/present ordering.

### 10.2 Beginner object, query, input, and event conveniences

- [x] Support scalar `move(x, y, z)` and `rotate(rx, ry, rz)` while retaining
  tuple/vector calls and physics transform rules.
- [x] Add `Game.raycast(...)`, `Entity.raycast(...)`, and viewpoint-aware
  `Player.raycast(...)` with optional advanced filters.
- [x] Add held-key and held-mouse access plus `Game.on_mouse(...)` without
  weakening action maps, edge semantics, or cancellable subscriptions.
- [x] Add beginner collision decorators with entity-only callbacks while
  preserving full `CollisionEvent` hooks.

### 10.3 Managed gameplay, timing, audio, and animation

- [x] Add `Entity.add_health(...)`, `Player.add_weapon(...)`, and one canonical
  health/weapon instance per entity.
- [x] Auto-advance owned weapons, timers, state machines, and tweens exactly
  once through the existing scheduler; retain standalone manual operation.
- [x] Add cached `Game.play_sound(...)` and validated `Entity.animate(...)`.
- [x] Define scene switch, entity destruction, pause, cancellation, clock, and
  exception behavior for every managed helper.

### 10.4 UI and package organization

- [x] Preserve one-constructor UI and contextual Row/Column/Grid/Stack layout;
  test nested adoption and cleanup.
- [x] Keep health and scoreboard widgets automatically synchronized without
  manual calls in ordinary use.
- [x] Add curated `easy3d.time`, `easy3d.scene`, and `easy3d.advanced` modules
  while retaining compatible root exports.

### 10.5 Learning path, compatibility, and validation

- [x] Add the seven required runnable beginner examples and a 14-lesson
  beginner-first documentation path.
- [x] Synchronize `features.md`, README, API contract, typing, decisions,
  known issues, and progress evidence with implemented behavior.
- [x] Pass native CTest, Python pytest, strict typing, editable install, old and
  new examples, and targeted backward-compatibility tests.
- [x] Rerun construction/native-boundary/renderer benchmarks, record hardware
  and commands, and investigate any material regression.
- [x] Perform visible Windows managed/manual loop, resize, input, physics, UI,
  audio, close, and repeated-lifecycle checks when interactive validation is
  available; otherwise mark each item UNVERIFIED.

## Phase 11 — AutoTexture and Advanced Materials

### 11.1 Density and deterministic UV mapping

- [x] Add global and per-object pixels-per-unit controls with a default of 16.
- [x] Implement world-scale tile, cube-atlas, sphere, and authored-UV modes.
- [x] Cover nonuniform, parent, mirrored, and runtime scale plus stable atlas
  reference dimensions and tangent handedness with native/Python numeric tests.

### 11.2 Safe missing-asset generation

- [x] Generate bounded PNG tile, sphere, cube-cross atlas, and neutral-normal
  templates without overwriting an existing file.
- [x] Generate authored-UV templates for inspectable OBJ and glTF inputs and
  reject model references without usable UVs.
- [x] Record deterministic sidecar identity, validate retained sidecars before
  regeneration, refresh only Easy3D-owned metadata, and reject incompatible
  reuse without writing either PNG.

### 11.3 Native advanced materials

- [x] Add tangent-space normal, roughness, metallic, emissive, and ambient
  occlusion maps with sRGB/data color-space separation.
- [x] Preserve OBJ/glTF material associations and glTF packed
  metallic-roughness channels.
- [x] Keep shadows, post-processing, instancing, and scalar material factors in
  the shared D3D11 shader path.

### 11.4 Cache, reload, and Python integration

- [x] Add shared CPU/GPU texture caches with mipmaps and nearest filtering by
  default, plus a linear override.
- [x] Detect texture changes at a bounded polling interval, retain the previous
  valid image on decode failure, update all sharers, and replace GPU handles.
- [x] Release expired shared GPU handles and scene-owned CPU model/texture
  caches; verify repeated scene cleanup returns D3D11 texture telemetry exactly
  to baseline.
- [x] Expose typed constructor and `MeshRenderer` runtime settings while keeping
  the one-filename beginner call sufficient.

### 11.5 Evidence and documentation

- [x] Add generation, mapping, tangent, color-space, cache, recovery, model, and
  compatibility regressions; pass the native and Python suites.
- [x] Add `examples/13_autotexture`, visually verify its D3D11 output and shared
  hot reload, and publish exact run instructions.
- [x] Add renderer CPU/GPU/texture telemetry and record AutoTexture construction,
  cache-hit, reload, draw-call, frame-time, and memory measurements.
- [x] Synchronize README, `features.md`, API/architecture/decision/known-issue
  documentation, and exact progress evidence.
- [ ] Independently validate visual output on additional D3D11 hardware and the
  minimum supported Visual Studio 2022 toolchain.

## Phase 12 — Double-sided rendering and face culling

- [x] Add typed `double_sided` and `cull_mode` constructor/runtime APIs for
  primitives, models, entities, and `MeshRenderer`, including conflict errors.
- [x] Apply back/front/no-cull material state in ordinary, instanced, and shadow
  submissions while preserving mirrored-transform winding semantics.
- [x] Honor explicit model override, glTF material `doubleSided`, then back-cull
  fallback precedence without changing geometry, physics, or raycasts.
- [x] Correct two-sided lit and tangent-space normal-mapped shading with
  front-facing fragment information and no additional shader permutations.
- [x] Add native/Python regressions, type-check coverage, focused examples, and
  actual Windows D3D11 visual/instancing validation.
- [x] Synchronize README, feature/API/architecture/decision/known-issue,
  changelog, progress, and master-plan documentation.
- [ ] Independently validate visual output on additional D3D11 hardware.

## Phase 13 — Advanced lighting, multiple light sources, and skyboxes

### 13.1 Scene-owned skyboxes

- [x] Add a typed, scene-owned `Skybox` API with a `Game.skybox` proxy,
  procedural top/horizon/bottom colors, brightness, rotation, and `None` to
  disable it.
- [x] Support equirectangular 2:1 panoramas and conventional six-face cubemap
  folders/mappings with deterministic validation and runtime replacement.
- [x] Generate bounded missing panorama/cubemap PNG templates atomically and
  never overwrite user assets.
- [x] Render translation-invariant, rotation-responsive sky behind geometry in
  the same HDR/post-processing/FXAA target and release replaced scene assets.

### 13.2 Bounded multi-light rendering

- [x] Extend native and typed Python lights with multiple directional, point,
  and spot sources plus live position, direction, color, intensity, range,
  cone-angle, enabled, and shadow controls.
- [x] Add preset-based light budgets, deterministic relevance ordering,
  camera/frustum culling, and active/culled renderer diagnostics.
- [x] Apply every supported light kind coherently to scalar, textured, model,
  instanced, normal-mapped, PBR-map, emissive, and two-sided materials.

### 13.3 Per-light shadows

- [x] Preserve directional shadows and add selectable spot-map and six-face
  point-cubemap shadows with per-light enable, resolution, and bias.
- [x] Enforce bounded preset shadow budgets with deterministic selection,
  dropped-caster/pass/memory telemetry, and clean runtime recreation.

### 13.4 Evidence and developer experience

- [x] Add native/Python unit and integration coverage for skybox validation,
  generation, mutation, cleanup, light math/culling/budgets, and shadows.
- [x] Add beginner tutorials, a combined visual example, and a repeatable
  lighting benchmark; synchronize README, features, API, architecture,
  decisions, known issues, and progress evidence.
- [x] Pass native CTest, Python pytest/type checks, editable install, existing
  examples, benchmark regression checks, and interactive Windows D3D11 visual
  validation without regressing earlier phases.
- [ ] Independently validate visual output on additional D3D11 hardware.

## Phase 14 — Universal entity motion and facing

- [x] Store reset-on-reuse velocity, acceleration, angular velocity, and
  angular acceleration in every native entity slot with finite-value checks.
- [x] Integrate ordinary entities on the fixed clock with semi-implicit Euler,
  stable world-axis quaternion deltas, and world-space parent conversion.
- [x] Delegate dynamic/kinematic/character motion to Jolt, including additive
  acceleration, degree-based rigid angular velocity, upright character yaw,
  and attachment/removal transfer.
- [x] Preserve or explicitly reset motion through teleport, freeze/restore it
  across disable/enable, and reject moving collider-only static entities.
- [x] Expose typed live motion, speed/direction/facing/launch helpers, separate
  Player view vectors, and breaking `move_speed`/`move_acceleration` tuning.
- [x] Add native and Python motion regressions, constructor coverage, type
  stubs, the projectile tutorial, and synchronized API/feature/decision docs.
- [x] Pass final Debug and Release CTest, complete pytest and mypy, editable
  install, and interactive Windows projectile validation.
- [ ] Independently validate motion and projectile rendering on additional
  Windows/D3D11 hardware.

## Working protocol

1. Inventory the dirty tree and preserve unrelated user changes.
2. Make one bounded architectural change at a time.
3. Build and test frequently; fix regressions rather than bypassing them.
4. Keep public stubs, docs, examples, tests, and native bindings synchronized.
5. Record exact commands, outputs, failures, and manual-validation limits.
6. Do not add dependencies, publish artifacts, push commits, or modify the
   global machine without explicit approval.

## Phase 15 — RIX rebrand and Pygame Community Edition integration

### 15.1 Audit and presentation decision gate

- [x] Establish the pre-migration pytest, Debug/Release CTest, typing, package,
  toolchain, and dependency baseline.
- [x] Audit standalone SDL3/bgfx ownership and document reuse/adaptation risks
  in `docs/pygame-integration-plan.md`.
- [x] Prototype Pygame CE 2.5.8 HWND attachment with one bgfx D3D11 presentation
  owner and validate it on an actual Windows/NVIDIA D3D11 renderer.
- [x] Prototype buffered offscreen readback to a Pygame Surface and measure
  correctness/latency before accepting the public viewport API.

### 15.2 Rebrand and package migration

- [x] Make `rix`/`rix._rix` the authoritative distribution, package, extension,
  documentation, example, test, and benchmark identity without resetting 0.1.0.
- [x] Retain a warning-only `easy3d` compatibility facade over the same modules
  and native runtime; test mixed imports and resource identity.
- [x] Add pinned optional `pygame` installation metadata while keeping base and
  standalone installations independent of Pygame.

### 15.3 Pygame-owned application adapter

- [x] Add `World` external stepping, bounded fixed updates, render/present
  ownership, close/lifetime rules, statistics, scene/camera/physics access, and
  no internal sleep or Pygame queue drain.
- [x] Translate supplied Pygame keyboard, mouse, wheel, controller, focus,
  resize, and quit events while preserving ordinary Pygame polling.
- [x] Support first-/third-person controls and configurable mappings without
  SDL3 pumping in Pygame-owned mode.

### 15.4 Data and hybrid rendering interoperability

- [x] Accept finite Pygame Vector2/Vector3 and useful Rect values without a hard
  runtime dependency in core math/entity APIs.
- [x] Copy Pygame Surface RGBA data into owned native textures, support explicit
  updates, and verify channel/alpha/pitch/lifetime/cache behavior.
- [x] Add camera-independent offscreen `Viewport` targets and buffered Surface
  readback with explicit performance limitations.
- [x] Add camera-facing/constrained-axis billboards and Pygame overlay
  composition with depth, alpha, DPI, resize, and resource-lifetime tests.

### 15.5 Evidence, examples, and release readiness

- [x] Migrate retained standalone examples and add all required Pygame/hybrid,
  migration, physics, viewport, billboard, menu, and mini-game examples using
  public APIs only.
- [x] Run package/shim, event, timing, Surface, readback, viewport, billboard,
  composition, lifecycle, standalone, native, Python, and typing regressions.
- [x] Benchmark standalone/GPU/Surface modes and upload/readback workloads at
  representative scene sizes with recorded hardware and exact commands.
- [ ] Complete actual Windows resize/input/overlay/physics/fullscreen/close and
  repeated-lifecycle checks; leave unsupported claims explicitly unverified.
- [x] Synchronize README, features, API, architecture, decisions, known issues,
  progress, changelog, setup, and migration documentation with verified RIX
  behavior.

## Phase 16 — Multiplayer framework and state systems

The numbered checklist below is the execution ledger for the approved
multiplayer/state goal (source SHA-256
`717CDEE23DC8D41B4800DEFBA8448C3EC137EF5F3D6D2D56CE1ABE57A1C37292`).
An item is checked only after its implementation and relevant validation pass.

### 16.1 Audit and architecture

- [x] 16.1.1 Confirm the current `rix` package has no public networking API and
  establish the retained Python regression baseline.
- [x] 16.1.2 Inspect historical Easy3D transport, dedicated/listen server,
  discovery, replication, RPC, prediction, test, example, and benchmark work.
- [x] 16.1.3 Preserve the RIX renderer/physics/Pygame conversion and selectively
  adapt reusable networking code instead of reverting the worktree.
- [x] 16.1.4 Synchronize architecture, dependency/license, API, security,
  known-issue, feature, and developer-setup documentation.

### 16.2 Native transport and safe messaging

- [x] 16.2.1 Restore pinned GameNetworkingSockets 1.6.1 and Protobuf 5.29.3
  behind optional `RIX_ENABLE_NETWORKING` and a networking-disabled stub.
- [x] 16.2.2 Restore reliable/unreliable delivery, bounded queues/messages,
  connection lifecycle, timeouts, metrics, protocol/schema handshake, and
  gameplay-thread polling callbacks.
- [x] 16.2.3 Add `rix.net.Session` named messages with safe basic-value JSON
  schemas, explicit client/send-to/broadcast routing, handler removal, and no
  pickle or arbitrary object execution.
- [x] 16.2.4 Add named schema registration, per-message validation declarations,
  and documented malformed-message disconnect policy.

### 16.3 Hosting and connection arrangements

- [x] 16.3.1 Restore real direct-IP clients and headless fixed-tick dedicated
  servers with independent authoritative scene ownership.
- [x] 16.3.2 Restore listen servers with an isolated real local-client identity
  and no duplicate authoritative simulation.
- [x] 16.3.3 Restore bounded opt-in IPv4 LAN discovery and compatibility fields.
- [x] 16.3.4 Add polished separate client/server entry points and actual
  independent-process Session acceptance tests.
- [x] 16.3.5 Implement and validate IPv6 where supported.
- [x] 16.3.6 Implement a functional optional self-hosted signaling/relay
  reference backend; do not claim room-code connectivity before it passes.

### 16.4 Replication, RPC, and authoritative real-time play

- [x] 16.4.1 Adapt stable object IDs, registered prefabs, spawn/despawn,
  ownership, dirty typed variables, snapshots, deltas, late joins, and cleanup.
- [x] 16.4.2 Adapt registered bounded RPC schemas, direction, sequence, ownership,
  rate-limit, and server-validation behavior.
- [x] 16.4.3 Adapt transform interpolation, spatial interest, bandwidth budgets,
  bounded baselines/resync, and per-client telemetry.
- [x] 16.4.4 Adapt supported native character input sequencing, prediction,
  correction/reconciliation, and remote interpolation.
- [x] 16.4.5 Revalidate all adapted replication/RPC/prediction suites against
  current RIX entity, movement, scene, and scheduler APIs.
- [x] 16.4.6 Define explicit deterministic snapshot/restore contracts before
  implementing lockstep or rollback; never claim generic Jolt/Python rollback.

### 16.5 StateMachine simplification and entity ownership

- [x] 16.5.1 Preserve `add_state`, `add_transition`, `start`, `trigger`,
  and manual `update` compatibility.
- [x] 16.5.2 Add initial-state construction, `@state`, `change`, current/
  previous/elapsed state, pause/resume/reset, and safe deferred changes.
- [x] 16.5.3 Add prioritized conditional transitions, bounded loop prevention,
  enter/exit decorators, cancelable state-local timed transitions, and
  consistent callback-exception state.
- [x] 16.5.4 Add `Entity.state_machine(initial)` over the existing exactly-once
  managed scheduler lifecycle.
- [x] 16.5.5 Complete destroyed/disabled/detached lifecycle and duplicate
  advancement tests plus state-machine performance measurements.

### 16.6 GameStates, overlays, and animation

- [x] 16.6.1 Add Pygame-friendly `GameStates` registration and optional
  enter/exit/update/fixed-update/event/draw forwarding.
- [x] 16.6.2 Add safe deferred screen changes, push/pop overlays, stable
  bottom-to-top drawing, suspended underlying updates, timers, and cleanup.
- [x] 16.6.3 Add configurable update/draw/input propagation and explicit screen
  ownership policies.
- [x] 16.6.4 Add animation selection that does not restart unchanged clips and
  connect optional state animation metadata only to actually supported runtime
  animation behavior.
- [x] 16.6.5 Add explicit local-versus-server-authoritative replicated match
  state integration and synchronized deadlines.

### 16.7 Security, performance, examples, and completion

- [x] 16.7.1 Complete malformed traffic, replay, rate, ownership, connection,
  queue/backpressure, timeout, reconnect, and exception cleanup validation.
- [x] 16.7.2 Run deterministic impairment and real multi-process latency/loss/
  jitter/reorder/disconnect tests.
- [x] 16.7.3 Measure 2/8/16/32-client tick, latency, bandwidth, CPU, memory,
  queue, snapshot, and correction results without guaranteeing unmet targets.
- [x] 16.7.4 Publish the 13 required real multiplayer examples and keep load
  harnesses outside public examples.
- [x] 16.7.5 Publish the 10 required state/screen/server examples and beginner
  tutorials, starting with the smallest working programs.
- [x] 16.7.6 Pass Debug/Release native, complete Python, strict typing, editable
  install, wheel, single-player, Pygame, headless, and interactive independent
  client/server regression gates.
- [x] 16.7.7 Synchronize every maintained document with only verified behavior
  and produce the final implementation/security/performance/limitations report.

## Phase 17 — FBX importing and skeletal animation

This numbered checklist is the execution ledger for the FBX and skeletal
animation goal supplied on 2026-11-08. An item is checked only after its
implementation and relevant native, Python, asset, or interactive validation
passes. The mandatory acceptance asset pair is the Mixamo YBot model and
Thriller animation identified by the asset audit.

### 17.1 Repository and asset audit

- [x] 17.1.1 Preserve unrelated worktree changes and establish Python,
  Debug/Release native, package, typing, and toolchain baselines.
- [x] 17.1.2 Import the original YBot and Thriller source assets without
  altering them, fingerprint their bytes, and document format/version/content.
- [x] 17.1.3 Inspect skeleton names, hierarchy, bind/rest poses, units, axes,
  embedded media, clips, root motion, and direct/retargeted compatibility.
- [x] 17.1.4 Publish `ASSET_AUDIT.md` beside the external animation test and
  preserve the source FBX files outside the engine repository.

### 17.2 Reproducible ufbx and static FBX importing

- [x] 17.2.1 Pin ufbx v0.23.1/commit
  `26a482ae66871d7de36eb722aa060bce95bce274` in CMake and record its license.
- [x] 17.2.2 Load binary and ASCII FBX through the shared model cache with
  actionable parse errors and safe malformed-input handling.
- [x] 17.2.3 Import triangulated multi-mesh geometry, normals, UVs, colors,
  node/geometry transforms, bounds, coordinate axes, and units into `ModelData`.
- [x] 17.2.4 Import supported FBX base-color/PBR/normal/emissive/transparency/
  double-sided materials and external or embedded textures with documented
  fallbacks.
- [x] 17.2.5 Preserve verified OBJ and glTF/GLB behavior and caching.

### 17.3 Shared skeletons, weights, and clips

- [x] 17.3.1 Extend shared meshes with validated four-influence joint indices
  and normalized weights, reporting dropped or malformed influences.
- [x] 17.3.2 Import FBX joint hierarchy, rest/local bind transforms, inverse
  binds, skin clusters, mesh-to-skeleton transforms, and skeleton identity.
- [x] 17.3.3 Import every FBX animation stack through deterministic baked local
  TRS clips, preserving nonzero ranges, timing, quaternion continuity, and
  root metadata.
- [x] 17.3.4 Add hierarchy/rest/bind-aware compatibility mapping and bounded
  Mixamo rest-pose/axis/scale correction with actionable incompatibility errors.
- [x] 17.3.5 Reuse the same skeleton, clip, pose evaluation, blending, and
  external-animation runtime for FBX and glTF/GLB.

### 17.4 Native playback and visible skinning

- [x] 17.4.1 Add independent per-render-instance playback state, automatic
  scheduler advancement, loop/clamp/reverse, pause/resume/stop/restart, and
  exactly-once completion events.
- [x] 17.4.2 Add interruption-safe local-pose blending and hierarchical global
  pose/palette evaluation.
- [x] 17.4.3 Implement D3D11/bgfx GPU skinning for positions, normals, and
  tangents with bounded palette transport and explicit diagnostics/limits.
- [x] 17.4.4 Skin directional and point shadow passes and keep lighting,
  normal/PBR materials, culling, bounds, postprocessing, and cleanup correct.
- [x] 17.4.5 Support multiple independently animated instances sharing immutable
  model/texture/clip data, with a bounded native CPU fallback where required.
- [x] 17.4.6 Implement explicit in-place/default and opt-in root-motion modes
  without double-applying physics or transforms.

### 17.5 Python, Pygame, and examples

- [x] 17.5.1 Add typed public `Model.play()`, `add_animation()`, pause/resume/
  stop, speed/loop/blend/root-motion, state/time/duration, and completion APIs.
- [x] 17.5.2 Support compatible external FBX and glTF/GLB animation-only files
  using public APIs and clear skeleton errors.
- [x] 17.5.3 Advance animation exactly once in standalone `Game`, Pygame `World`,
  and independent viewport rendering.
- [x] 17.5.4 Create the external `animation test/main.py` acceptance program
  with public APIs, automatic looping, camera, lighting, floor/shadows, and
  documented controls; keep its FBX assets outside the engine repository.

### 17.6 Tests, performance, documentation, and acceptance

- [x] 17.6.1 Add native importer/skeleton/weights/sampling/blending/retargeting/
  skinning/invalid-input/lifetime tests, including the real asset pair.
- [x] 17.6.2 Add Python playback/external-clip/callback/independent-instance/
  scene/Pygame tests and synchronized type stubs.
- [x] 17.6.3 Prove distinct valid deformed YBot poses, looping, restart, repeated
  load/unload, and compatibility against the real YBot/Thriller assets.
- [x] 17.6.4 Benchmark truthful 1/10/100-instance CPU/GPU animation, shadows,
  loading, memory, draw calls, and frame costs on recorded hardware.
- [x] 17.6.5 Publish FBX, skeletal-animation, retargeting, Mixamo, Pygame, root
  motion, feature/API/architecture/decision/progress/known-issue documentation.
- [x] 17.6.6 Pass final editable install, package integrity, Python regression,
  Debug/Release native, focused typing, and retained OBJ/glTF/Pygame gates.
- [x] 17.6.7 Interactively validate and capture the actual YBot visibly
  performing Thriller on Windows/D3D11, including animated shadows and cleanup.
