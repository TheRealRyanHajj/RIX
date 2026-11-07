# RIX architectural decisions

## 2026-11-05 — Collidable geometry and readable default lighting

- World-space `Cube`, `Sphere`, `Plane`, `Model`, and `Billboard` constructors
  create colliders unless `collider=False` is explicit. Models default to a
  triangle mesh and accept `True` as `"mesh"`. Parented or universally moving
  visuals opt out because native static colliders cannot be parented or moved.
- Automatic scenes use low blue ambient, an elevated warm shadow-casting key
  directed through the initial camera octant, and a nearly horizontal cool
  fill across the opposite X/Z octant. A custom directional light atomically replaces both,
  so this readability rig does not contaminate authored lighting.

## 2026-11-05 — RIX identity and Pygame ownership

- `rix`/`rix._rix` are authoritative; the deprecated `easy3d` facade aliases
  modules in `sys.modules` and never loads a second `.pyd`.
- Pygame owns application lifecycle, timing, queue consumption, polling, and
  default audio. RIX's external session does not initialize or pump SDL3.
- Direct GPU mode makes bgfx the sole presenter. Pygame drawing uses an explicit
  uploaded overlay Surface; display flip/update is prohibited.
- Surface mode makes Pygame the sole presenter. Full-window output uses bgfx's
  supported BLIT_DST/READ_BACK flow synchronously. Independent Viewports use
  request-owned staging textures and pixel buffers, a bounded pending queue,
  cached output, and explicit blocking/nonblocking refresh behavior. Native
  storage is not reclaimed until bgfx reports the completion frame.
- Surface pixel memory is always copied and revisioned. Automatic per-frame
  upload is rejected to avoid hidden full-frame copies.
- Internal `easy3d` C++ namespaces/include paths and legacy CMake target names
  remain implementation details for now; renaming them provides no public
  value and would create needless ABI/source churn.

## ADR-0001: Pin native dependencies through CMake

All third-party source revisions are immutable. Native dependencies stay
private behind RIX types and are not installed as public SDK components.

## ADR-0002: Support Windows D3D11 first

SDL3 owns the native window and bgfx owns rendering. D3D11 is the supported
backend. Interactive graphics claims require a real Windows desktop check.

## ADR-0003: Keep renderer lifecycle on the window thread

Window creation, event polling, bgfx submission, resize/reset, and teardown run
on the gameplay/window thread. This makes ownership deterministic and avoids
cross-thread SDL/bgfx shutdown races.

## ADR-0004: Use world-scoped generational entity handles

Public wrappers never expose storage addresses. World ID, slot index, and
generation reject stale and cross-scene access.

## ADR-0005: Own the math and asset boundary

RIX value types and immutable asset records form the API. GLM,
tinyobjloader, cgltf, bimg, and bgfx types remain private.

## ADR-0006: Use native traversal with guarded Python callbacks

Native code owns traversal and fixed stepping. Python callbacks run at explicit
safe points with deferred snapshots and bounded catch-up behavior.

## ADR-0007: Give each scene a lazy Jolt world

Physics resources are scene-owned RIX handles. Contacts are queued as
immutable snapshots; characters, constraints, and bodies never leak Jolt
objects to Python.

## ADR-0008: Keep beginner conveniences compositional

Default scenes, primitives, players, gameplay helpers, and UI use the same
production components and native resources as explicit code. Defaults are
context-local, owned, and removable.

## ADR-0009: Remove networking from the product

The transport, GameNetworkingSockets/Protobuf dependency chain, protocol,
client/server wrappers, LAN discovery, replication, remote calls, match state,
prediction/reconciliation, online examples, benchmarks, and tests were removed
as one breaking simplification. Local character movement retains ordinary
jump, sprint, crouch, slope, and step behavior but no longer carries sequence
or correction state.

The resulting engine has a smaller build graph and a narrower security and
maintenance surface. Reintroducing online functionality requires a separate
approved design rather than compatibility shims in the core.

This decision was superseded by ADR-0015 after the separately approved
2026-11-06 multiplayer/state-system goal.

## ADR-0015: Restore networking as an optional layered subsystem

RIX restores the previously verified GameNetworkingSockets transport without
reverting the Pygame/package overhaul. Native transport, Session messaging, and
replicated game state are separate testable layers. `rix.net` is the coherent
public namespace; single-player code does not need to import it, and headless
messaging must not initialize graphics. Unsafe pickle/object deserialization is
forbidden. Direct IP and LAN discovery are implemented; hosted relay, NAT
traversal, and generic rollback are not claimed.

## ADR-0010: One persistent frame step for managed and manual loops

`Game.run()` and `Game.tick()` share a native `WindowSession` frame step. The
manual API does not recreate SDL/bgfx per frame and does not implement a second
Python simulation clock. Native input, scheduler callbacks, fixed physics,
render submission, presentation, and counters therefore retain one ordering.

Manual code may mutate the active scene only between ticks on the owning
gameplay thread. Recursive tick, concurrent managed/manual control, and closing
inside a frame are errors. A context-managed manual loop is the preferred form
because it deterministically tears down a partially completed session.

## ADR-0011: Beginner helpers compose existing ownership

Scene-free raycasts delegate to `rix.physics`; attached health is the
existing `Health`; managed weapons use `HitscanWeapon`; one-call audio uses the
game's `Audio` cache; and animations use `Tween`. Managed registrations are
cancellable handles and entity-owned registrations end with entity or scene
attachment lifetime. Standalone manual APIs remain supported.

## ADR-0012: Preserve input intent across clock boundaries

Native action state retains both edges when a control is pressed and released
within one SDL polling frame. The built-in `Player` samples the jump edge on
the render update and keeps a one-shot request until the next fixed simulation
tick. General `Game.on_input` callbacks also dispatch during render update so
interaction edges do not disappear on a frame with no fixed tick. Held
movement, sprint, and crouch remain fixed-step reads. This avoids lost input
intent when render FPS exceeds physics Hz without advancing physics from
variable-rate Python code.

## ADR-0013: Use simple projection-based character movement

The automatic `Player` latches a jump press edge until one fixed tick consumes
it, but never resubmits a held button. The native motor has no coyote or jump
buffer timers. A jump succeeds only on a walkable grounded tick and skips ground
friction on that exact takeoff tick, making bunny hopping a timing mechanic.

Ground and air acceleration fill only the velocity projection along normalized
wish direction. Air movement caps that projection rather than total horizontal
speed and applies no friction, permitting strafe turns and emergent speed gain
without a special momentum-preservation branch. Grounded non-jump movement uses
Source-style friction before acceleration. Sprint and crouch only change wish
speed; an optional explicit horizontal cap is disabled by default.

## ADR-0014: Treat texture filenames as declarative material inputs

Primitive constructors resolve one texture filename into deterministic mapping,
generation, companion-map discovery, sampler, and color-space state before the
native scene mutation. Missing local PNGs are generated once with a sidecar;
existing files and user-owned metadata are never rewritten. Cube atlases use
`rix-cube-cross-v1`; ordinary cube/plane surfaces tile; spheres use their
authored spherical UVs; imported models preserve authored UVs.

If a generated PNG pair is deleted while its sidecars remain, both sidecars are
validated before either PNG is recreated. Compatible RIX-owned sidecars are
refreshed to the new pixel dimensions; incompatible or malformed metadata fails
without a partial image write, while valid user-owned metadata remains intact.

Cube atlas rectangles are derived once from the positive world dimensions used
to create or attach the atlas. The dimensions travel with the native render
component instead of being recomputed from every transform. This preserves the
PNG's face identity under runtime/parent nonuniform scale. Conflict checks
compare normalized face regions, so a uniform resolution/density change is
compatible while a different cuboid proportion is rejected.

Native `ImageData` objects remain stable while their decoded contents and
revision advance during hot reload. GPU cache entries key on that stable object
and sampler, replacing the handle in place when the revision changes. This
updates every sharer without reconstructing entities or growing one GPU entry
per reload. Albedo/emissive data is sampled as sRGB; normal, roughness,
metallic, and AO data remains linear. D3D11 normal maps use the DirectX green
channel convention. Tangent reconstruction also multiplies by the model
determinant sign so supported mirrored transforms preserve the normal-map basis.

Map discovery uses a neutral scalar factor of one for roughness, metallic, and
emission when the caller omits the scalar. With no map, the established scalar
defaults remain `0.5`, `0`, and `0`. GPU texture entries retain weak CPU owners;
expired entries are destroyed after frame submission rather than accumulating
until renderer shutdown.

## ADR-0015: Model face visibility as retained material state

Face culling belongs to each render material and its shadow submission, not to
generated geometry or collision shapes. RIX's CCW front winding maps back,
front, and no-cull modes to D3D11 through bgfx, with a front/back swap for
mirrored world transforms. Cull mode is part of the instancing compatibility
key, so instances share a draw only when their effective state matches.

The high-level `double_sided` property is an alias for no culling. Conflicting
explicit alias and `cull_mode` values fail immediately. Imported models resolve
explicit override before glTF `doubleSided` before the back-cull fallback; an
override deliberately applies across all parts. Shadow passes follow the same
effective cull decision as the visible material. Back-face lighting reverses
the final reconstructed normal through `gl_FrontFacing`, including the
normal-mapped path, without adding shader permutations.

## ADR-0016: Fixed-budget forward lights and scene-owned fullscreen skies

RIX uses one bounded forward-light array instead of hidden per-light draw
passes or an unbounded shader interface. Presets cap directional/point/spot
sources at `1/4/2`, `2/16/8`, `4/32/16`, and `4/64/32`; deterministic native
culling and priority decide admission. The initial shadow budget is one source
of each direct kind, keeping cost and telemetry predictable while the public
API can describe more lights than a frame admits.

Point shadows store normalized radial distance in six R32F cubemap faces. The
D3D11 path resolves overlapping casters with a minimum blend into a white-cleared
face instead of attaching an incompatible per-face 2D depth target; sampling
then compares receiver distance with the selected cubemap direction. Spotlights
use a rotated cone bounding box for conservative frustum relevance.

Skyboxes are scene resources, not entities: they have no transform hierarchy,
physics, collision, or gameplay identity. Fullscreen ray reconstruction keeps
the sky translation-invariant without cube geometry and submits into the main
post-processing target. Missing sky generation has its own sidecar identity
and never uses AutoTexture density. Generated cubemap faces evaluate one
directional gradient so shared edges agree rather than assigning unrelated face
colors.

## ADR-0017: Convert display-authored colors at the HDR boundary

Python-facing material, light, and procedural-sky colors are authored as sRGB
display values. When the renderer uses its linear floating-point post-process
target, it converts those values to linear light before shading; the final
post-process pass remains responsible for tone mapping and display encoding.
The direct-to-backbuffer fallback retains its existing display-space behavior.
Texture albedo and emissive inputs continue to use hardware sRGB decoding, so
they are not manually converted a second time.

## ADR-0018: Make motion universal, world-space, and fixed-step

Every native entity slot owns linear/angular velocity and acceleration, even
without physics components. Linear motion uses world units and angular motion
uses degrees at the Python boundary. Ordinary entities use semi-implicit Euler
on the existing fixed clock; world-axis rotation deltas avoid Euler drift and
parented results are converted back to local transforms.

Jolt remains authoritative for rigid bodies and characters. Motion transfers
when ownership changes, acceleration is additive to gravity, and teleporting
preserves state unless explicitly reset. Characters retain upright collision,
so only yaw angular motion is accepted. Facing is always an explicit command:
velocity, acceleration, and collision response never rotate an entity.

`Player` separates character tuning (`move_speed`, `move_acceleration`) from
universal entity vectors and exposes camera-aware view axes separately from
body-facing axes. The rename is intentionally breaking before 1.0; rejected
legacy scalar calls provide direct migration guidance rather than guessing.

## ADR-0019: Require an isolated deterministic contract before rollback

RIX does not treat arbitrary Python, ordinary entities, or Jolt simulation as
cross-process deterministic. A future rollback system must operate on an
application-supplied fixed-tick model with canonical bounded byte snapshots,
complete restore, registered ticked inputs, stable digests, deterministic
random state, deferred side effects, and bounded history/replay. Independent
process digest/replay/resynchronization tests are a release prerequisite.

The full contract is `docs/rollback-contract.md`. The current native character
prediction path is intentionally narrower and is not described as rollback.
