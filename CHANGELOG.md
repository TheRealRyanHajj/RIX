# RIX changelog

All notable private releases are recorded here. RIX follows Semantic
Versioning while it remains pre-1.0; compatibility and release procedure are in
[docs/release.md](docs/release.md).

## Unreleased

- Made built-in world geometry collidable by default, with `collider=False`
  retained for decoration, parented visuals, and non-physics motion.
- Replaced the washed-out single default sun with a low-ambient warm key/cool
  fill rig that gives differently oriented faces distinct shading.
- Corrected the D3D11 front-face normal sign in solid and textured shaders;
  ordinary outward normals were previously flipped inward, leaving upward and
  key-facing surfaces ambient-only. Rebalanced the rear fill and changed the
  first Pygame example's near-black navy material to a readable medium blue.
- Reduced the automatic directional key's shadow bias from `0.002` to `0.0005`
  to prevent contact shadows from making grounded objects appear suspended.
- Renamed the public distribution/package/native module to RIX, retaining
  version 0.1.0 history and a warning-only `easy3d` compatibility facade over
  the same native runtime.
- Added Pygame CE 2.5.8 integration with Pygame-owned loop/events, direct HWND
  D3D11 presentation, fixed-step external updates, event/controller forwarding,
  resize/focus handling, and deterministic shutdown.
- Added copied/revisioned Pygame Surface textures, dynamic updates, Pygame
  vector/Rect interoperability, alpha overlay composition, camera-facing
  billboards, synchronous full-window RGBA GPU readback, and camera-independent
  preview Viewports with bounded buffered readback and cached output.

- Added universal native fixed-step velocity, acceleration, angular velocity,
  and angular acceleration to every entity, including world-space parenting,
  physics/character delegation, freeze/resume, transfer, and teleport policy.
- Added entity speed/facing/direction/launch helpers, camera-aware Player view
  axes, degree-based Rigidbody angular velocity, and assignable character
  linear velocity. Player tuning now uses the breaking `move_speed` and
  `move_acceleration` names with migration errors for legacy scalar keywords.
- Corrected the HDR color-space boundary for authored material, light, and
  procedural-sky colors, restoring clear directional shading between cube
  faces; direct-light specular highlights are now suppressed on unlit faces.
- Removed multiplayer and networking in full: native transport/protocol code,
  heavy backend dependencies, Python online APIs, prediction/reconciliation,
  examples, benchmarks, tests, and obsolete documentation. This is a breaking
  pre-1.0 simplification with no compatibility stubs.
- Reintroduced networking as the separately approved optional `rix.net`
  subsystem: pinned GameNetworkingSockets transport, safe Session messages,
  listen/dedicated servers, numeric IPv4/IPv6, IPv4 LAN discovery, registered
  replication/RPC, interest/bandwidth controls, native character prediction,
  authoritative match state, deterministic impairment, and a self-hosted
  room-code signaling directory. Hosted matchmaking, packet relay, arbitrary
  NAT traversal, and generic rollback remain explicit non-features.
- Added simplified StateMachine decorators/conditions/timers, entity-owned
  lifecycle, Pygame-friendly GameStates stacks/overlays, animation selection,
  ten state examples, thirteen multiplayer examples, and eleven focused
  multiplayer/state tutorials.
- Replaced assisted character hopping with a simpler Source-style motor:
  normalized wish input, ground friction, projection-based ground/air
  acceleration, an air projection cap, edge-triggered jumping, and frictionless
  landing-frame takeoff. Removed coyote time, jump buffering, and held-jump
  auto-hop; sprint/crouch now change wish speed without cropping momentum.
- Added beginner-owned Game defaults, optional first-/third-person Player
  controls, primitive physics and transform shortcuts, named/hex colors,
  direct UI construction, callbacks, and timers.
- Added hierarchy/entity helpers, physics shortcuts, composable gameplay
  helpers, contextual retained UI layouts, and task-oriented examples/guides.
- Q/E and Tab remain bindable input actions; Q/E no longer rotate the obstacle
  course player.
- Dispatch input callbacks on every rendered frame so short interaction presses
  are not lost when no fixed physics tick occurs in that frame.
- Added AutoTexture filename-only PNG generation, world-scale tile/atlas/sphere
  mapping, authored OBJ/glTF UV templates, normal/roughness/metallic/emissive/AO
  maps, mipmaps, shared hot reload, runtime primitive material settings, and
  renderer CPU/GPU/texture telemetry.
- Stabilized cube-atlas face regions across parent and runtime nonuniform scale,
  made map-backed scalar defaults neutral, and release shared GPU texture
  handles when their final scene/cache owner disappears.
- Validate retained generated sidecars before recreating deleted PNG pairs,
  refresh only RIX-owned metadata, and leave user metadata untouched.
- Correct tangent-space handedness under mirrored model transforms and remove a
  callback-adapter ownership cycle that delayed default-scene cleanup.
- Added double-sided, front-face, and back-face rendering controls to
  primitives, imported models, entities, and mesh renderers; glTF authored
  `doubleSided`, shadows, mirrored transforms, normal mapping, and instancing
  use the same effective culling policy.
- Added scene-owned procedural, equirectangular, and cubemap skies with safe
  missing-asset generation; added bounded multiple directional/point/spot
  lighting, native relevance culling, live controls, local/directional shadows,
  renderer telemetry, examples, tutorials, and stress benchmarks.

## 0.1.0 — 2026-11-01

Initial private Windows x64 release with the native C++20 engine, typed Python
API, D3D11 rendering through SDL3/bgfx, scene/entity lifecycle, assets, cameras,
lighting, HUD, audio, physics, diagnostics, and CPython 3.11–3.13 wheels.
