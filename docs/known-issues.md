# RIX known issues and validation limits

## Pygame integration

- Pygame-owned rendering currently supports Windows x64/D3D11 only and one
  active bgfx renderer session per process.
- Full-window Surface readback and the first/default blocking Viewport image
  synchronize with the GPU. The recorded 320x180 one-cube full-window sample
  took 11.764 ms on the validation machine; full-window use can be much slower.
  Later default Viewport refreshes use bounded native buffered requests and may
  intentionally return the previous cached frame.
- Each Viewport has an independent camera and exact-size target, but all
  Viewports share one renderer thread and scene. Submitting many large previews
  still adds render work and GPU-to-CPU bandwidth; at most eight unconsumed
  native readbacks may be pending at once.
- GPU mode requires a separate overlay Surface and forbids
  `pygame.display.flip()`/`update()`. Drawing directly on the display Surface is
  not composited by bgfx.
- Programmatic windowed/fullscreen/windowed transitions passed on the recorded
  D3D11 machine, but interactive Alt-Tab/fullscreen appearance, controller
  hot-plug on physical hardware, high-DPI fractional scaling, maximize visuals,
  and device-loss recovery remain unverified.
- Billboard alpha/depth and free/Y-axis facing passed automated state and one
  local GPU smoke path, but dense billboard performance is not yet benchmarked.
- Call `world.close()` before `pygame.quit()`. Destroying the Pygame HWND first
  is invalid lifecycle ordering and raises or may provoke driver-specific
  teardown behavior.

## Interactive validation

Automated tests cannot prove visual appearance, mouse feel, gamepad behavior,
speaker output, or device hot-plug behavior. These require a GUI-capable Windows
desktop and real hardware. Recorded evidence is hardware-specific and does not
guarantee behavior on every driver or device.

The automated manual-loop smoke proves native frame counts, callback counts,
and clean teardown on the recorded D3D11 machine, but it does not by itself
prove perceived smoothness, resize appearance, or input feel. Those remain
interactive checks.

During the 2026-11-02 Phase 10 validation, an initial Windows capture failed
with `foreground window did not report a process id`; resetting the helper
resolved it. The recovered run visibly verified D3D11 rendering, resize,
keyboard input, physics content, retained UI callbacks, and clean window
shutdown. Speaker audibility remains unverified even though SDL3 device/voice
state and automated audio tests passed.

An isolated Python/native `native_add` sample initially appeared slower, but a
controlled five-sample comparison using the retained pre-change and current
artifacts measured 216.6 and 205.0 ns/call respectively. The performance gate
uses the controlled result; all benchmark values remain hardware-specific.

## Windows build environment

Editable native builds require an MSVC x64 developer environment. A normal
PowerShell session may select an unsupported MinGW compiler if it appears first
on `PATH`. Visual Studio versions newer than 2022 have worked in local testing,
but that does not independently prove the minimum Visual Studio 2022 baseline.

The first CMake configure requires internet access to fetch immutable dependency
commits. Later rebuilds can use the populated build cache.

## Renderer and shaders

The supported renderer is Windows D3D11. Committed shader binaries target that
backend. Debug bgfx output is verbose. Shadows and post-processing are bounded
quality features rather than a physically based rendering suite.

Graphics-disabled builds retain asset metadata tests but do not decode texture
pixels or exercise GPU resources.

## Assets and skeletal animation

glTF/GLB and FBX skeletal models now visibly skin through D3D11, but only that
backend is verified. GPU palettes are limited to 64 joints; larger rigs use a
bounded native CPU fallback with 32 MiB vertex and 8 MiB index transient pools.
Model parts are deformed once and reused across passes, but enough simultaneous
large CPU-skinned instances can still exhaust that explicit frame bound. Four
greatest influences are retained and dropped weights are diagnosed. Animated
models conservatively bypass bind-pose frustum culling, so large crowds can cost
more than static instances.

FBX embedded/layered textures are not extracted and unsupported transparency
modes fall back to opaque with warnings. Blend shapes, facial/morph animation,
IK/constraints, semantic humanoid retargeting, and arbitrary deformers are not
supported. Compatible-rig retargeting requires joint names and parents plus
bounded rest transforms; it is not a general cross-rig solver.

The real 52-joint YBot uses GPU skinning. CPU fallback is benchmarked only with
a generated 65-joint, three-vertex technical fixture; no representative
redistributable >64-joint character is present, so that result is path overhead,
not large-rig throughput. The 100-YBot Ultra/shadow run on the recorded RTX
3070 Ti averaged 138.4 ms/frame and is not a 60 Hz capacity claim. Historical
benchmark evidence now lives with the external animation-test project.

AutoTexture can draw UV-island outlines for OBJ files it can inspect directly.
For JSON glTF it currently generates a deterministic 256x256 authored-UV grid,
not colored island boundaries; GLB containers are imported but are not rewritten
or used for missing-texture template extraction. Imported model UVs are
preserved and runtime primitive material overrides are supported, but per-part
runtime material replacement for imported models is not yet a public API.

Automatic companion discovery uses `_normal`, `_roughness`, `_metallic`,
`_emissive`, and `_ao` PNG suffixes. Newly created companions are discovered by
new render components; deleting a currently attached map does not silently
detach it. Hot reload is local-filesystem polling (250 ms minimum in the render
loop), not an OS directory-watcher service.

The visual AutoTexture check was completed on one NVIDIA D3D11 device
(`vendor=0x10de`, `device=0x2482`). Exact material appearance remains
driver/monitor dependent. The run verified atlas separation, spherical/tiled
mapping, normal/PBR paths, and a shared-texture live replacement. It does not
prove every face orientation or tangent convention on other hardware.

Face-culling visual validation was completed on the same NVIDIA D3D11 device.
It covered ordinary back culling, front-cull inward shells, normal-mapped
two-sided interiors, shadows, and cull-state instancing separation/merging.
Exact winding/driver behavior remains independently unverified on other D3D11
hardware. Imported models may contain mixed per-part glTF `doubleSided` state;
the single `MeshRenderer.cull_mode` property represents the component override
or fallback, while authored per-part flags remain effective until an override
is assigned.

Generated cube-atlas proportions are fixed when the texture is created or
attached. Later nonuniform scaling intentionally stretches each face's artwork
within its original region instead of reallocating the user-owned PNG. Tiled
mapping remains the appropriate mode when constant texel density during dynamic
resizing is more important than unique per-face artwork.

## UI and audio

## Lighting and skybox validation limits

The D3D11 implementation budgets at most one directional, one spot, and one
point shadow caster per frame; additional requests are reported as dropped.
Point shadows use six hard radial-depth samples and can show seams/aliasing at
low resolutions. There are no cascaded sun shadows, area lights, image-based
lighting, reflection probes, volumetrics, or non-D3D11 backend claims.

Generated cubemap templates use a seam-matched direction-derived gradient and
are still intended for artist replacement. Panorama/cubemap skies do not
derive environment reflections or ambient irradiance. Visual output remains to
be independently checked on additional D3D11 hardware.

HUD text uses a bundled printable-ASCII atlas and intentionally basic layout.
Audio is a bounded PCM WAV mixer, not a streaming music, effects-processing, or
spatial-acoustics engine.

## Player and physics

The character controller supports timing-based bunny hopping and projection-based
air strafing, but it is not a bit-for-bit Source engine movement simulator.
Crouching, steps, slopes, friction, acceleration, air speed caps, and collision
responses should be tuned and interactively validated per game.

## Networking scope

The verified native backend is currently Windows/MSVC numeric IPv4/IPv6 direct
IP. LAN discovery is IPv4-only. RIX ships an optional self-hosted room-code
endpoint directory, but no hosted matchmaking, packet relay infrastructure, or
arbitrary NAT traversal. Character prediction is
implemented and tested for the current sprint/crouch motor, but remains a
motor-specific bounded reconciliation path rather than generic rollback for
arbitrary Python or Jolt simulations. Internet behavior beyond real loopback
and deterministic local impairment still needs independent multi-machine
validation.

The recorded dense 32-client replication benchmark exceeded the 16.67 ms 60 Hz
tick budget (38.908 ms p99). It is evidence of an unmet target, not a 32-player
60 Hz capacity claim. Interactive two-window authority/state/disconnect behavior
was visually verified; held-key multiplayer movement feel was not manually
judged by the UI automation and remains a target-hardware check.
