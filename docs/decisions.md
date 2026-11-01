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
Perspective projection takes vertical FOV, explicit near/far planes, aspect,
and a renderer-capability `homogeneous_depth` choice. The D3D path maps depth to
`[0,1]`; homogeneous depth maps to `[-1,1]`.

The renderer retains current pixel width/height and calculates aspect on every
geometry submission after SDL size events. Python exposes the same native math
through a typed standalone `Camera`; entity/component attachment is deferred
until that ownership API exists.

### Consequences

- GLM remains private while native and Python tests can inspect exact matrices.
- Resizing changes horizontal projection without distorting vertical FOV.
- A camera can be configured and validated before scene components are added,
  without inventing implicit global-camera ownership.
- Orthographic projection and multi-camera render targets are not claimed.

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
