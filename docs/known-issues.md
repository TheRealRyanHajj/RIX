# Easy3D known issues and validation limits

There are no remaining blockers to the Phase 0 exit gate on the validated
machine.

## Phase 1 is incomplete

Phase 1.1 scene/entity lifetime semantics and Phase 1.2 math/transform hierarchy
are implemented. Component attachment, meshes, cameras, materials, textures,
model loading, lighting, culling, and instancing remain unimplemented checklist
work. The loaded scene therefore owns entity and transform state but is not yet
submitted to the renderer.

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

## Debug bgfx output is verbose

Debug builds emit bgfx capability diagnostics and benign optional-tool notices
for components such as RenderDoc or AMD AGS when those tools are absent. Release
builds provide the concise selected-renderer and adapter log used by the example.

## Pinned GLM emits CMake policy deprecation warnings

GLM 1.0.1 is pinned by immutable commit and builds successfully, but its
upstream CMake project requests compatibility with CMake versions older than
3.10. CMake 4.0 therefore emits non-fatal deprecation warnings during a fresh
configure. Easy3D does not suppress or patch vendored warnings; a future reviewed
GLM pin update should re-evaluate them.

