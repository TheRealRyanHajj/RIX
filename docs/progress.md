# RIX implementation progress

## 2026-11-05 — Default colliders and readable beginner lighting

Changed `Cube`, `Sphere`, `Plane`, `Model`, and `Billboard` to create native
colliders by default. `Model()` defaults to a triangle mesh and accepts
`collider=True` as a `"mesh"` shorthand. `collider=False` remains the explicit
choice for decoration, parented visuals, or ordinary universal-motion entities;
those cases cannot safely own a moving/parented static Jolt shape. Internal
enemy visuals, tutorials, and Pygame examples now state that opt-out where
needed.

Replaced the automatic scene's high ambient/single directional source with a
lower ambient (`0.16`), elevated warm shadow-casting key (`0.95`) directed
through the initial camera octant, and neutral-cool non-shadowing fill (`0.55`) aimed
almost horizontally across the opposite X/Z octant. This gives the three
initially visible cube faces distinct light levels without leaving the rear
vertical faces near-black. Setting
`game.lighting.directional` preserves the key/fill ratio. The first custom
directional source destroys both defaults, so authored lighting remains fully
controlled by the developer.

Exact validation from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
.venv\Scripts\python.exe -m pytest tests\python\test_beginner_api.py tests\python\test_primitives.py tests\python\test_entity_motion.py tests\python\test_autotexture.py tests\python\test_pygame_surfaces.py tests\python\test_pygame_viewport.py -q
# exit 0; 65 passed in 1.20 s

.venv\Scripts\python.exe -m pytest -q
# first run: 1 failed, 214 passed; obstacle-course finish trigger inherited the
# new box collider and then attempted to attach a second sensor collider
# final exit 0 after explicit collider=False on that sensor visual;
# 216 passed in 14.25 s

.venv\Scripts\python.exe -m mypy
# exit 0; Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# exit 0; No broken requirements found.

.venv\Scripts\python.exe -m compileall -q python examples
# exit 0; no errors

.venv\Scripts\python.exe -c "import runpy, threading, pygame; threading.Timer(1.0, lambda: pygame.event.post(pygame.event.Event(pygame.QUIT))).start(); runpy.run_path(r'examples\pygame\01_cube.py', run_name='__main__'); print('RIX_CUBE_DEFAULT_LIGHTING_PASS')"
# exit 0; actual NVIDIA 0x10de/0x2482 Direct3D 11 renderer, medium preset;
# RIX_CUBE_DEFAULT_LIGHTING_PASS

.venv\Scripts\python.exe tests\manual\pygame_viewport_gpu.py
# exit 0; actual NVIDIA Direct3D 11 renderer;
# RIX_VIEWPORT_GPU_PASS front=d9fadaa94466e937 side=c73e59fe6ea188f3 buffered=true

.venv\Scripts\python.exe -m pip install -e ".[pygame,dev]"
# exit 0; rebuilt generated shaders and native extension;
# wheel 5,795,732 bytes, SHA-256
# 82b009ea71e6ace6130d564c3a098e063c2a1a5137ab89ac2316b2126eb9811f

.venv\Scripts\python.exe tests\manual\face_culling_gpu.py
# exit 0; face_culling_gpu: PASS separated=2/1 merged=1/1

.venv\Scripts\python.exe tests\manual\lighting_debug.py --seconds 1 --preset medium
# exit 0; lighting_debug: PASS, 2,776 frames, actual NVIDIA D3D11

.venv\Scripts\python.exe tests\manual\render_components.py --seconds 1
# exit 0; render_components: PASS, 2,651 frames, actual NVIDIA D3D11
```

A 640x480 D3D11 Surface-mode front/rear capture pair was inspected at
`build/default-lighting-front-final.png` and
`build/default-lighting-rear-final.png`. The faces have visibly distinct
shades on both camera octants. This confirms the reported flat-face problem is
corrected on the recorded GPU, not merely in light-registry unit tests.

Follow-up front/rear captures exposed and corrected a deeper D3D11 shader bug:
the renderer's winding/cull convention makes `gl_FrontFacing` false on the
ordinary surviving outward side, but both material shaders treated that branch
as a backface and inverted all normal vectors. Regenerated pinned DXBC now
preserves outward normals on ordinary geometry and flips only the reverse side
of two-sided/front-cull materials. The key was raised, the fill made nearly
horizontal and more neutral (`0.55`), and `01_cube.py` changed from near-black
`#060566` to readable `#6677dd`. Final sampled RGB values were front
top/left/right `(85,91,149)/(81,86,138)/(70,75,124)` and rear
`(85,91,149)/(50,65,142)/(52,68,147)` on the actual D3D11 renderer.

The first-person example's cubes are geometrically grounded: a unit cube at
`y=0.5` spans `y=0..1`, and its plane mesh is at `y=0`. The apparent Ultra-only
gap came from directional shadow peter-panning. The default key bias is now
`0.0005` instead of `0.002`, reducing separation across the 100-unit
orthographic shadow depth without moving or intersecting the geometry.

The first direct shader invocation used `--Werror` and failed because the
existing bounded light loops generate HLSL compiler warnings; rerunning with
the CMake-equivalent non-`--Werror` flags generated both headers successfully.
An attempted incremental extension build then re-entered a stale historical
MinGW CMake cache and could not locate pybind11. The supported isolated editable
install above rebuilt and installed the MSVC artifact successfully. The first
face-culling probe after rebuild counted the procedural skybox as a third draw;
the batching-only probe now disables that unrelated sky draw and passes its
original `2 -> 1` batch assertions.

## 2026-11-05 — RIX rebrand and Pygame CE integration

Completed the public rename from Easy3D to RIX. `rix` and the native
`rix._rix` module are authoritative; `easy3d` is a warning-only migration
facade over the same Python modules and native runtime. Packaging now pins
Pygame Community Edition 2.5.8 behind the `pygame` extra, uses canonical
`RIX_*` CMake options and `rix.*` CTest names, and retains the internal
`easy3d` C++ namespace/target paths only as private implementation and source
compatibility details.

Added a Pygame-owned `World` adapter with bounded fixed stepping, external HWND
attachment, D3D11 presentation ownership, Pygame event forwarding, controller
and player-control integration, statistics, resize handling, and deterministic
shutdown. The Surface bridge owns copied RGBA texture data and supports dynamic
updates. Hybrid rendering includes Pygame overlays, camera-facing billboards,
and independent-camera `Viewport` targets. Viewports cache exact-size render
targets and use request/poll/wait readbacks; polling advances one renderer frame
so a standalone Surface-mode viewport cannot remain pending when no main-world
render occurs.

Fourteen public examples cover the Pygame loop, first-person control, overlay,
static/dynamic surfaces, inventory and split viewports, billboards, menus,
physics, standalone mode, migration, and a hybrid mini-game. The migration
guide preserves an existing Pygame loop, sprites, fonts, mixer, controls, and
UI while adding either GPU-owned 3D presentation or a Surface-compatible
viewport.

Exact final validation commands from
`C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && cmake --build --preset windows-debug && cmake --build --preset windows-release'
# exit 0; both Debug and Release native trees built

cmd.exe /d /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && ctest --preset windows-debug --output-on-failure && ctest --preset windows-release --output-on-failure'
# exit 0; Debug: 14/14 rix.* tests passed in 1.87 s
# exit 0; Release: 14/14 rix.* tests passed in 0.76 s

.venv\Scripts\python.exe -m pip install -e ".[pygame,dev]"
# exit 0; rix-0.1.0 cp311 win_amd64 editable wheel built and installed
# wheel size 5,795,624 bytes; SHA-256
# 076396ff5e16364932921da6781e916c38dd8905494fd18b6e1c690552560954

.venv\Scripts\python.exe -m pytest -q
# exit 0; 215 passed in 14.92 s

.venv\Scripts\python.exe -m mypy
# exit 0; Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# exit 0; No broken requirements found.

.venv\Scripts\python.exe -m compileall -q python examples
# exit 0; no output

.venv\Scripts\python.exe -c "import rix; print('RIX_IMPORT_PASS', rix.engine_version(), rix.__version__); import warnings; warnings.simplefilter('always'); import easy3d; print('EASY3D_SHIM_PASS', easy3d.engine_version())"
# exit 0; RIX_IMPORT_PASS 0.1.0 0.1.0
# DeprecationWarning: easy3d was renamed to rix; replace 'import easy3d' with 'import rix'
# EASY3D_SHIM_PASS 0.1.0

.venv\Scripts\python.exe tests\manual\pygame_viewport_gpu.py
# exit 0; Direct3D 11, NVIDIA vendor 0x10de/device 0x2482, medium preset
# RIX_VIEWPORT_GPU_PASS front=aca79a9426b51e10 side=77151150d13c982e buffered=true

.venv\Scripts\python.exe tests\manual\pygame_lifecycle.py
# exit 0; RIX_PYGAME_LIFECYCLE_PASS cycles=5

.venv\Scripts\python.exe tests\manual\pygame_physics_timing.py
# exit 0; RIX_PYGAME_PHYSICS_PASS ball_y=0.550 player_distance=4.423 jump_delta=0.569

.venv\Scripts\python.exe tests\manual\pygame_fullscreen.py
# exit 0; RIX_PYGAME_FULLSCREEN_PASS sizes=[(640, 360), (640, 480), (700, 420)] hwnd_changes=0

git diff --check
# exit 0; no whitespace errors; Git emitted only expected LF-to-CRLF warnings
```

All fourteen files in `examples\pygame` were executed with timed clean
shutdowns on the same Windows D3D11 system. Examples 01–11 and 14 received a
real Pygame `QUIT` timer event; standalone examples 12 and 13 used the public
RIX stop path. All fourteen exited 0. This is automated execution evidence,
not a claim that every control or visual was physically inspected.

Representative final benchmark commands and results (full table and hardware
notes are in `docs/benchmarks.md`):

```powershell
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode viewport --objects 100 --frames 20 --size 960 540 --viewport-size 256 256
# mean 0.859 ms; p95 1.171 ms; 1163.9 fps; working set 111,280,128 bytes

.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode viewport --objects 100 --frames 10 --size 960 540 --viewport-size 960 540
# mean 3.127 ms; p95 3.353 ms; 319.8 fps; working set 113,950,720 bytes

.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 0 --frames 60 --size 960 540 --physics-bodies 200
# mean 0.209 ms; p95 0.257 ms; update mean 0.960 ms; update p95 2.473 ms
```

An additional exploratory command, not the configured typing gate, remains
red:

```powershell
.venv\Scripts\python.exe -m mypy python tests/typecheck/public_api.py
# exit 1; 197 errors in 17 files
```

Those errors are pre-existing full-implementation annotation/stub debt (the
configured strict public-consumer gate above passes); they are not hidden with
a blanket ignore. A raw CMake build outside `VsDevCmd.bat` also failed because
MSVC standard-library include paths were unavailable. The documented developer
prompt command is the supported and passing path.

The actual D3D11 tests exercised HWND attachment, presentation, independent and
buffered readback, programmatic resize/fullscreen transitions, physics timing,
close, and five complete create/destroy cycles. Physical mouse and controller
input/hotplug, fractional high-DPI alignment, maximize visuals, Alt-Tab
fullscreen appearance, and graphics-device-loss recovery remain
**UNVERIFIED**. A live desktop visual-inspection attempt was stopped by the
user, so no interactive visual pass is claimed for those items.

## 2026-11-04 — Simple Source-style character movement

Replaced the assisted held-jump controller with normalized wish input,
Source-style ground friction, projection-based ground and air acceleration, an
air projection cap, and edge-triggered jumps. The native coyote and jump-buffer
timers were removed. Jumping on the first grounded landing tick skips friction,
so correctly timed bunny hops retain momentum; holding Space does not auto-hop.
Sprint and crouch alter wish speed without directly cropping existing velocity.
`horizontal_speed_limit=None` leaves emergent strafe gain uncapped by default.

The public `Player` and `CharacterController` tuning surface now exposes
`air_acceleration`, `ground_friction`, `stop_speed`, `air_speed_cap`, and
`horizontal_speed_limit`. The previous `air_control`, `coyote_time`, and
`jump_buffer_time` parameters were removed as an intentional pre-1.0 break.

Exact validation commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmake --build --preset windows-release --parallel 4
# exit 1: invoked outside the MSVC developer environment; cl could not find cstddef

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && cmake --build --preset windows-release --parallel 4'
# exit 0

ctest --preset windows-release --output-on-failure
# initial exit 0; after test-isolation fix, final exit 0;
# 100% tests passed, 0 failed out of 14; 0.42 s

ctest --preset windows-debug --output-on-failure
# initial exit 1: the air-strafe regression left 3 m/s velocity active long
# enough to leave the finite test floor; the test now resets its character
# before later checks. Final exit 0; 100% passed, 0 failed out of 14; 0.76 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && .venv\Scripts\python.exe -m pip install --no-deps -e .'
# exit 0; editable rix-0.1.0 cp311 win_amd64 wheel built and installed

.venv\Scripts\python.exe -m pytest tests\python -q
# exit 0; 200 passed in 19.84 s

.venv\Scripts\python.exe -m pytest tests\python\test_character_controller.py -q
# exit 0; 9 passed in 0.21 s

.venv\Scripts\python.exe -m mypy
# exit 0; Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# exit 0; No broken requirements found.

.venv\Scripts\python.exe -c "import rix; print(rix.engine_version()); s=rix.Scene(); p=rix.Player(scene=s, controls=False); print(p.controller.air_acceleration, p.controller.ground_friction, p.controller.air_speed_cap); s.clear()"
# exit 0; 0.1.0; 8.0 6.0 1.5
```

The first import smoke attempted `Player(controls=False)` without an active or
explicit scene and correctly raised the documented `RuntimeError`; rerunning
with `scene=Scene()` passed. No interactive keyboard/feel validation was run for
this change, so TF2/HL2-like tuning quality remains **UNVERIFIED** pending a
desktop playtest.

## 2026-11-03 — Universal entity motion and facing

Implemented zero-initialized native motion state for every entity: world-space
linear velocity/acceleration and degree-based angular velocity/acceleration.
Ordinary entities use semi-implicit Euler on the fixed clock with normalized
world-axis quaternion deltas and parent-local reconstruction. Dynamic and
kinematic bodies delegate actual velocity to Jolt; character controllers accept
external linear motion/acceleration and upright yaw. Physics attachment,
removal, teleport, disable/enable, and entity-slot reuse preserve or clear state
according to the documented policy.

The typed Python surface adds live motion vectors, `speed`, facing axes,
movement direction, direction conversion, `face_direction()`, `launch()`, and
`teleport(..., reset_motion=...)`. `Player` adds view axes and now separates
character tuning as `move_speed`/`move_acceleration`; legacy scalar keywords
raise migration guidance. All concrete entity constructors accept motion.

Exact validation commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && cmake --build --preset windows-debug && ctest --preset windows-debug --output-on-failure'
# exit 0; final rerun: 100% tests passed, 0 failed out of 14; 1.19 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && cmake --preset windows-release && cmake --build --preset windows-release && ctest --preset windows-release --output-on-failure'
# exit 0; final rerun: 100% tests passed, 0 failed out of 14; 0.83 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul && .venv\Scripts\python.exe -m pip install -e ".[dev]" --config-settings=build-dir=build/scikit-build-msvc/{wheel_tag}'
# exit 0; editable wheel 3,303,658 bytes; SHA-256
# f603ed1e053add2ae4f116b1a64ae7d3e759f1122986abfc080a255a2b231455

.venv\Scripts\python.exe -m pytest tests/python -q
# exit 0; final rerun: 199 passed in 15.26 s

.venv\Scripts\python.exe -m pytest tests/python/test_entity_motion.py -q
# exit 0; final post-install rerun: 11 passed in 0.22 s

.venv\Scripts\python.exe -m mypy
# exit 0; Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# exit 0; No broken requirements found.

.venv\Scripts\python.exe -c "import rix; print(rix.engine_version()); assert rix.engine_version() == rix.__version__; print('motion import smoke passed')"
# exit 0; 0.1.0; motion import smoke passed

.venv\Scripts\python.exe -c "import runpy; from rix import Game; original=Game.run; Game.run=lambda self: (self.after(2.0, self.stop), original(self))[1]; runpy.run_path(r'examples\beginner\13_projectile_motion.py', run_name='__main__'); print('projectile timed shutdown passed')"
# exit 0; Direct3D 11, NVIDIA 0x10de/0x2482, medium preset;
# projectile timed shutdown passed

git diff --check
# exit 0; only Git line-ending conversion warnings
```

Interactive Windows inspection opened `examples\beginner\13_projectile_motion.py`
in a native D3D11 window and visibly confirmed the floor/obstacle scene,
continuous ordinary-entity motion, and multiple yellow physical projectiles
moving and colliding after camera-aimed input. A timed second run exercised
normal `Game.stop()` and renderer/audio teardown with exit 0. Desktop-control
resize/Close clicks were rejected as concurrent user input while the player
owned pointer capture, so this checkpoint does not claim a new resize result;
resizing remains covered by earlier interactive engine validation. The first
inspection process was stopped after the helper conflict, while the timed
validation process exited cleanly on its own.

Two toolchain attempts failed before the supported path passed: building the
preset outside a developer prompt could not find C++ standard headers, and the
Community prompt did not expose `cl`, causing scikit-build to select MinGW and
fail. The installed Build Tools prompt plus a separate MSVC build directory
resolved both without changing global configuration. An initial native freeze
regression exposed and fixed a snapshot-order bug (pause was set before reading
velocity). The earlier five primitive/collider Python failures were separate
dirty-tree regressions; restoring non-physics primitive defaults to
`collider=False` resolved them, and the complete suite now has no failures.

## 2026-11-03 — Linear-light rendering correction

Corrected a renderer color-space error that sent display-authored material,
light, and procedural-sky colors directly into the linear HDR target. The
renderer now converts those values from sRGB at the HDR boundary while leaving
the direct-to-backbuffer fallback unchanged. Solid and textured shaders also
gate specular response on positive `N dot L`, preventing highlights from a
light behind a surface. The D3D11 shader headers were regenerated with the
pinned local bgfx `shaderc`.

Exact validation commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-debug --parallel'
# exit 0; native engine, bindings, and tests linked

ctest --preset windows-debug --output-on-failure
# 100% tests passed, 0 failed out of 14; 0.40 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-release --parallel'
# exit 0; native engine, bindings, and tests linked

ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 failed out of 14; 0.92 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && .venv\Scripts\python.exe -m pip install --no-deps -e .'
# exit 0; editable rix-0.1.0 wheel built and installed

.venv\Scripts\python.exe -m pytest -q
# 183 passed, 5 failed in 15.38 s. The failures are pre-existing dirty-tree
# primitive/physics regressions: automatic colliders on parented/visual cubes
# and a duplicate obstacle-course finish collider; none exercise rendering.

.venv\Scripts\python.exe -m pytest tests\python\test_lighting_debug.py -q
# 3 passed in 0.10 s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe examples\beginner\02_spinning_cube.py
# Direct3D 11, NVIDIA 0x10de/0x2482, medium preset; interactively inspected
# the rotating cube and confirmed distinct dark and directly lit side faces;
# closed cleanly through the native window controls.

.venv\Scripts\python.exe examples\15_lighting_sky\main.py --sky procedural --seconds 3
# exit 0; PASS frames=430 lights=1/3/1 culled=0 shadow_passes=8

git diff --check
# exit 0; only Git line-ending conversion warnings
```

## 2026-11-03 — Advanced lighting, local shadows, and skyboxes

Implemented scene-owned procedural, exact-2:1 panoramic, and six-face cubemap
skies with a `Game.skybox` proxy, live rotation/brightness, bounded exclusive
missing-PNG generation, replacement/disable cleanup, and a fullscreen native
sky pass that ignores camera translation and shares the post-processing target.
Generated cubemap faces now evaluate one direction-derived gradient so their
shared edges match; existing authored files are never rewritten.

Ambient, multiple directional, point, and spot lights now use common bounded
D3D11 shader arrays across solid, textured, imported-model, instanced,
normal/PBR-map, emissive, and two-sided paths. Point volumes and rotated spot
cone bounds are culled natively, then admitted by deterministic
shadow/relevance/handle priority under preset limits. High/Ultra support one
selected directional map, one spot map, and one six-face point cubemap per
frame, with live per-light resolution/bias and active/culled/pass/dropped/memory
telemetry. Point radial depth uses a white-cleared R32F cubemap with minimum
blending, avoiding an invalid mixed cubemap/2D framebuffer on D3D11.

Added `examples/15_lighting_sky` with procedural/panorama/cubemap modes, two
beginner examples, eight tutorial sections, `benchmarks/lighting.py`, expanded
native/Python tests, a GPU sky-lifetime probe, public `LightKind`, and synced
feature/API/architecture/decision/known-issue/changelog documentation.

Exact final commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-debug --parallel'
# exit 0; rix_core and all Debug native targets linked

ctest --preset windows-debug --output-on-failure
# 100% tests passed, 0 failed out of 14; 1.27 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-release --parallel'
# exit 0; rix_core and all Release native targets linked

ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 failed out of 14; 1.14 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && .venv\Scripts\python.exe -m pip install -e .[dev]'
# exit 0; editable wheel 3,291,768 bytes
# SHA-256 d51abc2b594810ae71c7feb703aa01ba659bf3d07f25e095e454a6c2530ebd74

.venv\Scripts\python.exe -m pytest -q
# 188 passed in 11.84s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe -m compileall -q python examples benchmarks
# exit 0, no output

.venv\Scripts\python.exe -m pip check
# No broken requirements found.

.venv\Scripts\python.exe -c "import rix; print(rix.engine_version()); print(rix.LightKind)"
# 0.1.0
# typing.Literal['ambient', 'directional', 'point', 'spot']

.venv\Scripts\python.exe examples\15_lighting_sky\main.py --sky procedural --seconds 3
# Direct3D 11, NVIDIA 0x10de/0x2482, high preset
# PASS frames=388 lights=1/3/1 culled=0 shadow_passes=8 shadow_bytes=48234496

.venv\Scripts\python.exe examples\15_lighting_sky\main.py --sky panorama --seconds 2
# exit 0; PASS frames=8 lights=1/3/1 culled=0 shadow_passes=8

.venv\Scripts\python.exe examples\15_lighting_sky\main.py --sky cubemap --seconds 2
# exit 0; PASS frames=54 lights=1/3/1 culled=0 shadow_passes=8

.venv\Scripts\python.exe tests\manual\skybox_gpu_lifetime.py
# PASS baseline=3/1398108 panorama=4/12582920 cubemap=4/7689564 released=3/1398108

.venv\Scripts\python.exe benchmarks\lighting.py --directional-lights 4 --point-lights 64 --spot-lights 32 --seconds 5 --preset ultra
# 2,938 frames/5.089 s = 577.28 FPS; active=4/64/32; 6 draws;
# 2 instanced draws; CPU=0.0368 ms; GPU=0.50176 ms

.venv\Scripts\python.exe benchmarks\lighting.py --directional-lights 6 --point-lights 70 --spot-lights 36 --seconds 2 --preset ultra
# 974 frames/2.098 s = 464.28 FPS; active=4/64/32; culled=12

.venv\Scripts\python.exe benchmarks\render_cubes.py --count 2000 --seconds 5
# 4,142 frames/5.114 s = 809.89 FPS; median/p95/p99=0.7698/2.057/3.0745 ms;
# 3 draws, 1 instanced scene draw, active lights=1/0/0

git diff --check
# exit 0; only line-ending conversion warnings, no whitespace errors
```

Interactive capture used the actual resizable SDL3/bgfx D3D11 window on the
NVIDIA device above. Procedural, generated panorama, and generated cubemap
modes were each visibly inspected. Captures showed the sky behind geometry,
red/green/blue point contributions on the same cube field, sun and spotlight
illumination, and cast shadows. Maximizing the procedural demo redrew the scene
at the new viewport size. The panorama and cubemap starter gradients rendered
with correct vertical orientation; the cubemap showed no visible generated-face
color discontinuity. Closing each window exited cleanly. This validates the
recorded machine only; other D3D11 hardware remains independently UNVERIFIED.

Failures found and corrected during completion:

- A plain `cmake --build --preset windows-debug` outside the MSVC developer
  environment failed with `fatal error C1083: Cannot open include file:
  'cstddef'`; invoking the pinned build through `VsDevCmd.bat` fixed the
  environment without a source workaround.
- The first point-shadow target paired each cubemap face with an independent
  2D depth texture; D3D11 rejected face 0 and the demo reported only two shadow
  passes. The final R32F minimum-blend design ran with all eight expected passes
  and 48,234,496 shadow bytes.
- The first GPU lifetime probe failed with `RuntimeError: Game has no active
  scene`; the probe now explicitly loads its test scene and passes.
- The first new malformed-cubemap assertion expected different wording
  (`same square dimensions` versus `cubemap skybox faces must use one size`).
  Matching the stable native message produced `4 passed` in the focused file.
- An exploratory full-package `python -m mypy.stubtest rix` remains blocked
  by broad pre-existing source-check errors outside the configured strict mypy
  surface (for example legacy variable-length tuple annotations and older
  physics stub signatures). The configured public-consumer mypy gate passes;
  the stubtest debt was not hidden with a blanket allowlist.

No Forward+/clustered path was added: measured fixed-budget forward evaluation
meets the current 100-light design target while retaining ordinary 2,000-cube
throughput near the approximately 800 FPS immediate baseline. Additional
D3D11 GPUs, non-D3D11 renderers, reflection/irradiance lighting, cascaded sun
shadows, soft point-shadow filtering, and the minimum Visual Studio 2022
toolchain remain outside this validation.

## 2026-11-03 — Double-sided rendering and face culling

Implemented one retained culling policy across primitives, imported models,
runtime entity/component properties, ordinary and instanced scene submission,
and shadow submission. The public `CullMode` literal accepts `"back"`,
`"front"`, or `"none"`; `double_sided=True` is the beginner shorthand for no
culling. Conflicting explicit values fail at construction. glTF material
`doubleSided` metadata is retained with explicit override, imported metadata,
then back-cull precedence. OBJ falls back to back culling.

The renderer verified RIX's CCW front winding and maps it to bgfx D3D11
state, swaps front/back for negative-determinant transforms, and includes cull
mode in material and shadow batch compatibility. Both lit fragment paths use
front-facing fragment state to reverse the complete back-face shading normal;
the textured path does this after tangent-space normal reconstruction. No
shader permutation or duplicate geometry was added, and physics/colliders/
raycasts remain unchanged.

Added `examples/beginner/10_inside_a_cube.py`, the multi-view
`examples/14_face_culling`, `tests/manual/face_culling_gpu.py`, Python contract
tests, native render/import tests, strict consumer typing, and synchronized
feature/API/architecture/decision/known-issue documentation.

Exact final commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-release'
# exit 0; Release native targets linked successfully

ctest --preset windows-debug --output-on-failure
# 100% tests passed, 0 failed out of 14; 0.53 s

ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 failed out of 14; 1.13 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && .venv\Scripts\python.exe -m pip install -e .[dev]'
# exit 0; editable wheel 3,265,988 bytes
# SHA-256 fa4cc0afbabd1ba8695593fadd7756639c220291293b3727fd3e9d75d612ed80

.venv\Scripts\python.exe -c "import rix; print(rix.engine_version()); print(rix.CullMode)"
# 0.1.0
# typing.Literal['back', 'front', 'none']

.venv\Scripts\python.exe -m pytest -q
# 183 passed in 9.44 s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# No broken requirements found.

.venv\Scripts\python.exe -m compileall -q python examples benchmarks
# exit 0, no output

.venv\Scripts\python.exe tests\manual\face_culling_gpu.py
# Direct3D 11, vendor=0x10de, device=0x2482, preset=low
# face_culling_gpu: PASS separated=2/1 merged=1/1
```

The first full Python run exposed nine existing convenience regressions after
the current branch had made primitive/model colliders implicit. The failures
included parented visuals gaining unsupported physics bodies, a duplicate
finish trigger, and the default `Model(..., collider=True)` being invalid.
Restoring the documented opt-in collider defaults reduced the run to one new
test error; that test was corrected to request the collider whose invariance it
checks. The final unfiltered run then passed all 183 tests. An initial Release
command also failed before execution because PowerShell parsed `(x86)` from an
incorrectly quoted command; using the established single-quoted `cmd.exe`
payload fixed the invocation without changing the build.

Interactive Windows validation used the actual D3D11 renderer on the NVIDIA
device above. `examples/14_face_culling` was inspected in all three views:
the outside view showed the normal back-culled cube, a cut-open front-culled
orange shell, a two-sided room, floor, and shadows; `inside-double` showed the
lit normal-mapped interior; and `inside-front` showed the inward-only interior.
The final outside capture also exercised explicit roughness/metallic factors on
the normal-mapped room and an unlit two-sided plane.
Bounded runs exited cleanly with 10–13 draw calls and approximately 5.55 ms
reported GPU frame time. The manual batching probe separately proved unlike
states split into two draws/one instanced draw and a runtime change to matching
state merged them into one draw/one instanced draw. Additional D3D11 hardware
validation remains unverified.

## 2026-11-03 — AutoTexture and advanced materials

Implemented filename-only missing PNG generation, deterministic tile/sphere/
cube-cross mappings, 16 px/unit global and per-object density, authored OBJ/glTF
UV preservation/templates, tangent generation with mirrored handedness, native
normal/roughness/metallic/emissive/AO sampling, sRGB/data separation, mipmaps,
shared hot reload, runtime primitive material mutation, renderer telemetry, and
`examples/13_autotexture`.

The completion audit added stable atlas reference dimensions: cube-cross regions
now retain the world proportions used to generate/attach the PNG while tile and
sphere modes continue following live composed scale. Parent/nonuniform runtime
scaling and normalized atlas-conflict regressions cover that distinction. The
same audit made discovered roughness/metallic/emissive maps use neutral scalar
factors, released expired shared GPU handles plus scene CPU caches, strengthened
all-six-face and sphere-seam numeric assertions, and removed a callback-adapter
ownership cycle that could defer default-scene cleanup until cyclic GC. It also
validates retained sidecars before regenerating a deleted base/normal PNG pair,
refreshes only RIX-owned metadata, and corrects tangent handedness under
mirrored model transforms in both textured vertex shaders.

The first native link failed with unresolved `bimg::imageGenerateMips`; adding
the already-fetched private `bimg_encode` target fixed the real dependency. A
first mirrored-UV assertion assumed a fixed negative sign; it was corrected to
test the invariant that mirroring flips handedness. A first filesystem cache
optimization delayed newly created companion discovery; the new test caught it,
and directory/metadata change stamps replaced the time-only cache.

Exact final commands from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --build --preset windows-debug && cmake --build --preset windows-release'
# exit 0; final mirrored-transform shader rebuild linked both configurations

ctest --preset windows-debug --output-on-failure
# 100% tests passed, 0 failed out of 14; 1.05 s

ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 failed out of 14; 0.83 s

cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && .venv\Scripts\python.exe -m pip install --no-deps -e .'
# exit 0; editable wheel 3,263,362 bytes; SHA-256 ce84ba09b86a51bc3f23a92b46330dbe59ad4723d36d760bd83671d4d091b7ae

.venv\Scripts\python.exe -m pytest -q
# 176 passed in 5.18 s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe -m mypy python/rix/autotexture.py
# Success: no issues found in 1 source file

.venv\Scripts\python.exe -m pip check
# No broken requirements found.

.venv\Scripts\python.exe -m compileall -q python examples benchmarks
# exit 0, no output

.venv\Scripts\python.exe benchmarks\autotexture.py --objects 2000 --cache-loads 10000
# generation 6.537 ms; construction 900.284 ms (450.142 us/object)
# 99.99% cache hit rate; 131.352 us/load; reload 0.892 ms

.venv\Scripts\python.exe tests\manual\autotexture_gpu_lifetime.py
# PASS baseline=3/1398108 loaded=17/2113524 released=3/1398108
```

Interactive Windows validation ran
`.venv\Scripts\python.exe examples\13_autotexture\main.py --seconds 30` on
D3D11/NVIDIA (`vendor=0x10de`, `device=0x2482`, high preset). Captures visibly
showed density-scaled cubes, tiled plane, separated six-color atlas, sphere,
OBJ/glTF geometry, and normal/PBR examples. Replacing one shared PNG while the
window ran changed all three sharing cubes together without a restart or crash.
The final-source bounded run exited 0 and reported `frames=786 draw_calls=18
instanced=1 cpu_ms=0.095 gpu_ms=5.556 textures=20
texture_bytes=2946376`.

Additional D3D11 devices, minimum Visual Studio 2022, GLB template extraction,
and per-part runtime material replacement remain unverified/not implemented as
documented in `docs/known-issues.md`.

Clean wheel builds and isolated wheel tests covered every declared Python ABI:

| Runtime | Isolated result | Wheel SHA-256 |
| --- | --- | --- |
| CPython 3.11 | `176 passed in 6.90s` | `addb2ecb4d37149615bf5b3c04a498a9407598528dd8ce5433a539bac5526e5e` |
| CPython 3.12 | `176 passed in 7.78s` | `3d0c3ec2d0ff6086d3ed6017e394ec43420b285159e5d7882c1268efb64b46ce` |
| CPython 3.13 | `176 passed in 6.93s` | `776a1257ffeadb04555f1bc249faf533cb6ac37c8bc3b82aee182d4a7f222081` |

The first new CPython 3.11 isolation attempt resolved the editable redirect and
was rejected as wheel evidence. The first CPython 3.13 attempt used
`PYTHONNOUSERSITE=1` without an isolated pytest target and failed with `No
module named pytest`. After adding test tools under `build/wheel-smoke`, a 3.13
run exposed a real callback-adapter ownership cycle through an intermittently
retained default scene (`1 failed, 174 passed`). The adapter now owns `Game`
weakly, and the final runs printed each wheel-local package and `.pyd` path
before passing. Test isolation explicitly collects intentionally abandoned
user-created callback cycles instead of depending on interpreter GC timing.

## 2026-11-02 — Interaction and momentum-preserving jump follow-up

Both beginner interaction examples were corrected. `07_simple_interaction.py`
now performs one raycast, uses a reliably camera-aligned target, destroys only
that target, and displays success/miss feedback. `07_interactions_and_triggers.py`
places the purple switch inside its documented interaction radius, binds E,
shows the control in the HUD, reports out-of-range attempts, and counts uses.
Direct desktop inspection showed the initial prompt and then
`Switch used 1 time(s)!` after activation. The user subsequently stopped the
desktop-control helper with physical Escape, so no further automated window
input was attempted in that session.

A follow-up found the remaining intermittent failure: `Game.on_input`
callbacks were sampled only by fixed updates, allowing a press on a 120 Hz
render frame with no 60 Hz physics tick to disappear. Input callbacks now run
during variable-rate update. A regression exercises a `1 / 120`-second frame,
asserts that zero fixed ticks ran, and still observes the interaction exactly
once. A fresh Windows D3D11 desktop run of
`examples\beginner\07_interactions_and_triggers.py` displayed
`Switch used 1 time(s)!` immediately after an injected E press.

This checkpoint originally added assisted held-jump buffering. It was
subsequently replaced by the edge-triggered, projection-based controller in the
2026-11-04 entry above; the old behavior is no longer present.

Verification from `C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
.venv\Scripts\python.exe -m pytest -q
# 167 passed in 5.90s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# No broken requirements found.

ctest --preset windows-debug --output-on-failure
# 100% tests passed, 0 failed out of 14; total time 0.39s

ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 failed out of 14; total time 0.97s
```

The final clean-wheel matrix also passed:

| Runtime | Test result | Wheel SHA-256 |
| --- | --- | --- |
| CPython 3.11.9 | `146 passed in 10.51s` | `6372885ad83c099d1ab9bbbddeec3361ddca4745f046c66e6ad4aa0fe1681f52` |
| CPython 3.12.10 | `146 passed in 12.10s` | `b844524fce86cd618cefc3425034e2eb3c6dc6b971942e366154f1c7fd01a1ee` |
| CPython 3.13.2 | `146 passed in 7.82s` | `3a59af0075b6992b22ba5dde468c8580601b54bd643d5f7ae71b3c37953f2727` |

## 2026-11-02 — VS Code editable-install and continuous rotation fix

The user's `.venv` was loading current editable Python files alongside a stale
9.3 MB native `_rix.pyd` that did not expose `Engine.tick()` or
`Engine.close()`. The supported MSVC developer-shell reinstall completed with:

```powershell
.venv\Scripts\python.exe -m pip install --force-reinstall -e '.[dev]'
# Successfully installed rix-0.1.0 and pinned development dependencies
```

Post-install introspection reports `Engine.tick True`, `Engine.close True`,
native version `0.1.0`, and the manual-loop example now launches and closes
with exit 0.

The spinning example exposed a separate transform defect: repeatedly reading
Euler angles back from the native quaternion made `cube.ry += 90 * dt` fold at
the +/-90-degree decomposition singularity. Entity rotations now keep a
scene-shared authored-Euler hint paired with the native quaternion, invalidate
it on external native changes, and clean it up with the entity. A regression
crosses 90 degrees, 360 degrees, and a second wrapper for the same entity.

Verification from the repaired `.venv`:

```powershell
.venv\Scripts\python.exe -m pytest -q
# 144 passed in 4.32s

.venv\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

.venv\Scripts\python.exe -m pip check
# No broken requirements found.
```

A two-second managed callback probe executed 345 updates and ended at
`ry=180.237879`, rather than plateauing near 90 degrees. Direct desktop checks
showed both `02_spinning_cube.py` and `03_manual_loop.py` visibly changing
orientation between captures and closing cleanly.

## 2026-11-02 — API simplification implementation and verification

Phase 10 now has one persistent native frame step shared by managed `run()` and
manual `tick()`, beginner movement/query/input/event conveniences, managed
gameplay and timing helpers, cached one-call audio, validated entity animation,
curated modules, seven required examples, and a 14-lesson learning path. The
public contract, type declarations, feature reference, decisions, and known
limits were updated with the implementation.

Latest automated verification from
`C:\Users\Ryan\Desktop\code\Easy3D`:

```powershell
build\venv311\Scripts\python.exe -m pytest -q
# 143 passed in 5.31s

build\venv311\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

build\venv311\Scripts\python.exe -m pip check
# No broken requirements found.

ctest --preset windows-debug
# 100% tests passed, 0 tests failed out of 14; total time 1.13s

cmake --preset windows-release
cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
# 100% tests passed, 0 tests failed out of 14; total time 1.29s
```

The first incremental Release invocation failed before compilation because a
previously interrupted configure had left `build-Release.ninja` referring to a
missing `CMakeFiles/impl-Release.ninja`. Regenerating with
`cmake --preset windows-release` repaired the build graph; the ensuing
582-step build and all 14 tests completed without a source workaround.

The final editable extension was rebuilt successfully with the installed MSVC
environment. The resulting wheel was
`rix-0.1.0-cp311-cp311-win_amd64.whl` (5,668,115 bytes), and pip reported
`Successfully installed rix-0.1.0`.

The real D3D11 scheduler/lifecycle smoke used:

```powershell
build\venv311\Scripts\python.exe tests\manual\manual_loop.py
```

Result: exit 0 on NVIDIA vendor `0x10de`, device `0x2482`:

```text
manual loop smoke: PASS (120 frames)
managed loop smoke: PASS (159 frames)
repeated lifecycle smoke: PASS (3 games)
```

The six managed examples from the required seven-example learning set were
executed through a validation wrapper that schedules `Game.stop()` after 0.05
seconds, then invokes their unmodified source via `runpy.run_path`. All six
initialized D3D11 and SDL audio and exited 0:

```text
examples\beginner\01_first_scene.py
examples\beginner\02_spinning_cube.py
examples\beginner\04_physics_playground.py
examples\beginner\05_first_person_game.py
examples\beginner\06_enemy_game.py
examples\beginner\07_simple_interaction.py
```

`examples\beginner\03_manual_loop.py` was also launched directly and remained
in its live manual loop until the validation process sent Ctrl+C. Its bounded
equivalent is covered by `tests\manual\manual_loop.py` above.

A broader D3D11 compatibility sweep executed every repository example except
the unbounded manual-loop source through the same scheduled-stop wrapper. The
native examples (`00`, `02`, `03`, `09`–`12`) and all managed beginner
examples exited 0. `01_entity_lifecycle` is a non-window lifecycle program and
also exited 0. The audio lesson was supplied a generated temporary PCM16 WAV.
The sweep found and fixed one genuine lesson bug: `06_state_machine.py` passed
an invalid empty string to `Text`; it now begins with `"State: idle"`. The
manual-loop source is covered by the direct launch and bounded native smoke
already recorded above.

### Performance evidence

The quiet post-change construction run was:

```powershell
build\venv311\Scripts\python.exe benchmarks\high_level_api.py --objects 2000
# construction objects=2000 high=0.087055s explicit=0.085317s ratio=1.020
```

The pre-change ratio was 1.049, so this sample shows no wrapper-construction
regression. A first isolated native-boundary rerun measured 163.4 ns/call at
1,000,000 iterations and 164.8 ns/call at 5,000,000 iterations versus the
single 118.0 ns/call baseline. That apparent regression did not reproduce in a
controlled artifact comparison: five warmed 5,000,000-call samples loaded the
retained pre-change and current `.pyd` files under the same Python and current
machine conditions. Their medians were 216.6 and 205.0 ns/call respectively.
The current binding was 5.4% faster in that controlled comparison.

The representative renderer workload was:

```powershell
build\venv311\Scripts\python.exe benchmarks\render_cubes.py --count 2000 --seconds 3
```

Current result: exit 0; 2,000 instances created in 0.057327 seconds, 3,611 frames in
3.083904 seconds, median sampled frame 0.6271 ms, p95 0.8375 ms, p99 1.0266 ms,
2 draw calls, 1 instanced draw call, 1,913 visible and 87 culled instances.
Working set was 27,160,576 bytes before creation, 28,274,688 after creation,
and 104,198,144 after the D3D11 run. The retained pre-change CPython 3.11 wheel
ran the identical command immediately beforehand: 0.065626-second creation,
0.6524/0.8870/1.0847 ms median/p95/p99 frames, the same 2 draw calls and 1
instanced call, and 30,781,440/32,583,680/108,605,440-byte working sets. The
current sample improved creation, frame percentiles, and final working set.

Scheduler traversal and native physics were compared with:

```powershell
build\wheel-smoke\cp311\Scripts\python.exe benchmarks\api_runtime.py
build\venv311\Scripts\python.exe benchmarks\api_runtime.py
```

The retained pre-change/current medians were 78.8/75.7 ns per registered
callback, 8,713.2/7,979.0 ns per scripted entity traversal, and
1,116.2/1,028.2 ns per body for the native physics step. Each current sample
was faster; no material Phase 10 regression was observed in the required
construction, callback, traversal, physics, memory, draw-call, or frame-time
workloads.

An initial invocation with unsupported `--output` failed with argparse exit 2;
the documented arguments were then used and the benchmark passed.

### Interactive Windows validation

After resetting the desktop-control session, direct inspection succeeded on
the D3D11/NVIDIA desktop:

- `examples\beginner\03_manual_loop.py` visibly rendered a lit, rotating blue
  cube. Maximizing the native window resized and reframed the render correctly;
  clicking Close terminated the Python process with exit 0.
- `examples\03_obstacle_course\main.py` visibly rendered the first-person
  course, steps, ramp, beams, finish trigger, and settled dynamic spheres.
  A synthetic same-frame Escape press stopped the rebuilt engine and the
  example exited 0. That validation found and drove fixes for same-frame action
  edges and fixed-tick jump latching.
- `examples\beginner\08_hud_menu.py` visibly rendered retained text, panel,
  Row, and buttons. Clicking Play changed `Choose an action` to `Playing!`;
  clicking Quit stopped the game and exited 0.
- Managed and manual modes, native Close/Alt+F4, resize, keyboard input,
  physics rendering, retained UI interaction, and repeated lifecycle are now
  directly verified on this machine.

SDL3 opened the default 48 kHz stereo float device, audio examples created
playback voices, and audio/cache tests pass. Whether sound was physically
audible through the user's speakers remains **UNVERIFIED** because this agent
cannot hear the device. This is recorded as a sensory limitation rather than
an inferred audibility claim; it does not negate the directly verified native
audio-device and voice lifecycle.

The input follow-up added a native regression for a down+up received in one
polled frame and a Python regression proving that automatic `Player` jump
requests survive a render frame with no fixed step. This raised the final
Python total at that checkpoint from 142 to 143 passing tests. The continuous
Euler regression added later raised the current total to 144.

### Python 3.11–3.13 wheel matrix

The complete supported matrix was last rebuilt after the networking removal,
API simplification, input fixes, editable-install repair, and continuous Euler
fix:

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\build_wheel_matrix.ps1'
```

Result: exit 0. Each wheel was installed into a freshly cleared venv with
`--no-index`, passed `pip check`, imported its native extension with matching
Python/native version `0.1.0`, and ran the complete suite:

| Runtime | Test result | Wheel SHA-256 |
| --- | --- | --- |
| CPython 3.11.9 | `146 passed in 10.51s` | `6372885ad83c099d1ab9bbbddeec3361ddca4745f046c66e6ad4aa0fe1681f52` |
| CPython 3.12.10 | `146 passed in 12.10s` | `b844524fce86cd618cefc3425034e2eb3c6dc6b971942e366154f1c7fd01a1ee` |
| CPython 3.13.2 | `146 passed in 7.82s` | `3a59af0075b6992b22ba5dde468c8580601b54bd643d5f7ae71b3c37953f2727` |

An additional ZIP-content audit found 31 files in each wheel, including the
matching `.pyd`, `_rix.pyi`, `py.typed`, project license, and third-party
notices. No headers, object files, static/import libraries, PDBs, or `_deps`
build-tree content were present. `build\wheelhouse\SHA256SUMS.txt` contains the
recorded hashes.

## 2026-11-02 — API simplification baseline

The Pygame-level API simplification phase began with a repository/API audit in
`docs/api-simplification-audit.md` and a Phase 10 checklist in `MASTERPLAN.md`.
No implementation claims are made at this checkpoint.

Current baseline commands and exact results:

```powershell
build\venv311\Scripts\python.exe -m pytest -q
# 132 passed in 6.11s

build\venv311\Scripts\python.exe -m mypy
# Success: no issues found in 2 source files

build\venv311\Scripts\python.exe benchmarks\high_level_api.py --objects 2000
# construction objects=2000 high=0.095629s explicit=0.091164s ratio=1.049

build\venv311\Scripts\python.exe benchmarks\native_add.py --iterations 1000000
# iterations=1000000 elapsed_seconds=0.117990 ns_per_call=118.0 final_value=500000
```

The visible renderer benchmark, manual loop, and new convenience APIs are not
yet implemented or validated. Interactive Windows results remain UNVERIFIED.

## Completed foundation and engine work

The repository contains a C++20 core, typed pybind11 package, SDL3/bgfx D3D11
window and renderer, scenes/entities/transforms, assets, cameras, lights,
culling/instancing, HUD/UI, input, scheduling, Jolt physics, first-/third-person
characters, audio, diagnostics, gameplay helpers, examples, tests, and Windows
wheel tooling.

Prior interactive Windows validation established that the native window opens,
resizes, renders, and closes on the tested D3D11 machine. That evidence is
hardware-specific; the networking-removal change still requires a new
interactive regression run before making a fresh visual claim.

## 2026-11-02 — Networking removal complete

### Scope removed

- GameNetworkingSockets, Protobuf, Abseil, and their CMake configuration.
- Native transport/protocol/client/server implementations and bindings.
- Python transport, discovery, replication, match-state, multiplayer-session,
  and prediction modules.
- Remote-input sequence/correction/replay hooks from the local character motor.
- Online examples, benchmarks, tests, public type exports, and third-party
  notices.
- Host/join/session methods from `Game` and obsolete online documentation.

### Scope retained

Rendering, local input, scenes/entities, physics, ordinary character movement,
jumping, sprinting, crouching, gameplay utilities, UI, audio, and assets remain
in scope.

### Automated verification

Commands ran from `C:\Users\Ryan\Desktop\code\Easy3D` on Windows x64 with
Python 3.11.9, CMake 4.0.1, Ninja 1.12.1, and Visual Studio 2026 Build Tools
18.11.3 / MSVC 19.51.36260.

```powershell
cmd.exe /d /s /c 'call "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && build\venv311\Scripts\python.exe -m pip install -e .[dev]'
```

Result: exit 0. Editable wheel built and installed as
`rix-0.1.0-cp311-cp311-win_amd64.whl`, 5,661,810 bytes. The configure/build
did not fetch or configure GameNetworkingSockets, Protobuf, or Abseil.

```powershell
build\venv311\Scripts\python.exe -m pytest -q
```

Result: exit 0, `132 passed in 7.89s`.

```powershell
build\venv311\Scripts\python.exe -m mypy
```

Result: exit 0, `Success: no issues found in 2 source files`.

```powershell
build\venv311\Scripts\python.exe -m pip check
build\venv311\Scripts\python.exe -c "import importlib.util, rix; print(rix.engine_version()); removed=('NetworkError','NetworkSession','Server','network','replication','PredictedCharacterController','ScriptRole','server_only'); assert not any(hasattr(rix, name) for name in removed); assert importlib.util.find_spec('rix.network') is None; assert importlib.util.find_spec('rix.replication') is None; print('removed API absent')"
```

Result: exit 0: `No broken requirements found.`, `0.1.0`, and
`removed API absent`.

```powershell
cmd.exe /d /s /c 'call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 && cmake --fresh --preset windows-debug && cmake --build --preset windows-debug && ctest --preset windows-debug'
```

Result: exit 0. A fresh 582-step Debug build completed; CTest reported
`100% tests passed, 0 tests failed out of 14` in 1.41 seconds. No native
network test target was generated.

The repository-wide implementation audit searched CMake, native code, bindings,
Python, tests, examples, benchmarks, scripts, and third-party notices for the
removed APIs/dependencies and returned no matches.

### Failures encountered and fixed

The first standalone preset invocation invalidated a stale compiler cache and
then failed to find `cl`. The Community developer command prompt did not contain
the installed compiler. Switching to the installed Build Tools prompt exposed
another stale cache entry pairing MSVC `cl.exe` with MinGW `ld.exe`. Running the
supported `cmake --fresh --preset windows-debug` re-detected MSVC `link.exe` and
the full build/test passed. No source bypass or test suppression was added.

### Validation status at that checkpoint

At the networking-removal checkpoint, the fresh interactive smoke and complete
Python 3.11–3.13 wheel matrix were still pending. Both were subsequently
completed during Phase 10; see the current evidence at the top of this file.
# 2026-11-06 — Multiplayer/state goal, recovery checkpoint

- Read the complete 1,620-line approved goal at
  `C:\Users\Ryan\.codex\attachments\d579bc45-dc28-4662-9e5e-5fc043f28319\pasted-text-1.txt`
  (SHA-256
  `717CDEE23DC8D41B4800DEFBA8448C3EC137EF5F3D6D2D56CE1ABE57A1C37292`).
- Baseline before networking edits:
  `.venv\Scripts\python.exe -m pytest -q` -> `216 passed in 18.76s`.
- Git history contained the prior complete native transport and substantial
  server/discovery/replication/RPC/prediction implementation. It was adapted
  selectively; current RIX rendering, physics, Pygame, lighting, and package
  work was not reverted.
- Restored pinned GameNetworkingSockets/Protobuf native sources and bindings
  behind `RIX_ENABLE_NETWORKING`; added `rix.net` and a bounded safe named
  message `Session` façade.
- MSVC configure:
  `VsDevCmd.bat -arch=x64 -host_arch=x64 && cmake --preset windows-debug`
  -> configured successfully with GameNetworkingSockets 1.6.1/BCrypt.
- MSVC build:
  `cmake --build --preset windows-debug --parallel 8` -> succeeded, 571 build
  steps after dependency configuration.
- Native tests: `ctest --preset windows-debug` -> `19/19 passed`, including
  network simulation, protocol, backend, client, and server tests.
- The exact editable command from an ordinary PowerShell initially selected
  MinGW 15.1 and failed compiling Protobuf
  `generated_message_tctable_lite.cc` with GCC musttail stack-slot errors.
  This unsupported path remains documented; it was not reported as passing.
- The same command in the installed MSVC developer environment,
  `.venv\Scripts\python.exe -m pip install -e ".[dev]"`, succeeded and
  produced `rix-0.1.0-cp311-cp311-win_amd64.whl` SHA-256
  `13523643f8fc36fd40b62271573311a850e68eb70eedba04fd336ad6b1bd2be0`.
- Native import evidence:
  `rix.net.backend_info()` ->
  `NetworkBackendInfo(available=True, name='GameNetworkingSockets',
  version='1.6.1', crypto_provider='Windows BCrypt')`.
- Adapted transport/server/listen/discovery plus new Session/codec coverage was
  added. A focused run reached 39 passed transport/server/listen tests; the
  complete suite then reached 260 passed with one stale discovery namespace
  expectation, which was corrected to `rix.net`.
- Added backward-compatible StateMachine decorators, conditions, priorities,
  timers, pause/reset, deferred changes and callback consistency; added
  entity-owned construction plus Pygame-friendly `GameStates` stacks.
- Focused state/discovery regression:
  `.venv\Scripts\python.exe -m pytest -q tests/python/test_utilities.py
  tests/python/test_simple_state_machines.py tests/python/test_discovery.py`
  -> `26 passed in 0.39s`.
- Next exact action: rerun the complete Python suite, then adapt and run the
  historical replication/RPC/prediction and independent-process gates before
  documenting the public networking and state APIs.

Follow-up evidence:

- Complete suite after state/GameStates and networking additions:
  `.venv\Scripts\python.exe -m pytest -q` -> `266 passed in 16.02s`.
- Adapted current-RIX replication lifecycle, typed NetworkVar, bounded RPC, and
  replicated match-state tests:
  targeted run -> `20 passed in 1.12s`.
- Complete suite after those additions:
  `.venv\Scripts\python.exe -m pytest -q` -> `286 passed in 17.63s`.
- Restored/adapted the real two-process direct-IP example and process harness:
  `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_two_process_network.py` -> `4 passed in 17.69s`.
- Prediction compatibility audit found that the RIX movement overhaul removed
  the historical native sequence/correction/replay hooks while adding
  sprint/crouch. Prediction is therefore explicitly UNVERIFIED and its old
  tests were not bypassed or falsely marked passing; the next implementation
  task is to merge those hooks into the current motor and then restore its
  regression suite.

Prediction and replication follow-up:

- Restored native character sequence, correction, and isolated replay hooks
  and extended their input contract with sprint/crouch. Native slot creation,
  destruction, clear, and reuse reset sequence/external-motion/pause state.
- Rebuilt with MSVC and reran `ctest --preset windows-debug
  --output-on-failure` -> `19/19 passed` in 1.86 seconds.
- Reinstalled with `.venv\Scripts\python.exe -m pip install -e ".[dev]"`
  inside the installed x64 MSVC developer environment -> exit 0; editable
  wheel SHA-256
  `8d4b2cd1a8adb61b50b2107234386f75c49fbf9980e1c16105312b4c3dbc8f2a`.
- `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_prediction.py` -> `7 passed in 0.22s`. This covers complete
  sprint/crouch intent replay, deterministic client/server motor parity,
  correction, stale sequence rejection, and native slot reuse.
- Complete Python suite immediately afterward -> `297 passed in 33.64s`.
- Restored/adapted transform interpolation, acknowledged delta baseline,
  recovery, interest budget, resynchronization, and ownership churn tests:
  `test_replication_resync.py test_replication_scaling.py` -> `6 passed in
  0.80s`; `test_network_conditions.py test_network_transform.py` -> `10 passed
  in 1.31s`.
- Added independent high-level `Session` routing/lifecycle coverage -> `2
  passed in 0.21s`.
- Fixed deferred initial StateMachine startup so initial enter decorators and
  `Entity.state_machine(initial)` work after attachment. State/utility focused
  run -> `17 passed in 0.19s`; entity factory focused run -> `7 passed in
  0.15s`.
- Updated the feature catalog, API contract, and known limitations to describe
  verified networking/prediction behavior and to remove the obsolete claim
  that RIX contains no networking API.

State/session/release follow-up:

- Added exact optional `Session.register_message()` schemas. Incoming schema
  violations and malformed frames disconnect the sender and raise
  `NetworkError`; focused codec/session suite -> `10 passed in 0.45s`.
- Added an actual independent-process high-level Session ping/pong gate -> `1
  passed in 0.97s`, plus separate headless server and Pygame client chat entry
  points under `examples/networking/01_pygame_chat`.
- Added `AnimationSelection` with no-restart-by-default semantics and wired
  StateMachine `animation=` metadata to entity selection. Documentation
  explicitly states that this is selection intent, not GPU-skinned rendering.
- Added all ten requested beginner state/screen examples under
  `examples/states`; eight graphics-independent programs were executed and all
  ten scripts passed compilation.
- Full Python regression after message, state, animation, prediction, and
  replication work: `.venv\Scripts\python.exe -m pytest -q` -> `321 passed in
  39.67s`. Mypy -> `Success: no issues found in 2 source files`; pip check ->
  `No broken requirements found.`; `git diff --check` reported no whitespace
  errors.
- The first fresh optimized native run compiled all Release dependencies and
  targets but the server test transiently exhausted its 100-port loopback
  range: `18/19 passed`. `--repeat until-pass:3` reproduced one failure then a
  pass. A subsequent complete `ctest --preset windows-release
  --output-on-failure` run passed `19/19` in 0.74 seconds. The transient is
  retained as evidence rather than hidden.
- Entity-owned machines now freeze while disabled and cancel on destruction or
  scene detach. Lifecycle/duplicate focused suite -> `10 passed in 0.15s`.
- Added a finite StateMachine benchmark. Test gate -> `2 passed in 0.35s`;
  measured default run: 250,000 updates at 6,493.0 ns/update, 50,000 changes at
  2,312.2 ns/change, 640-byte traced peak, correct=true. Values are local
  measurements, not platform guarantees.

GameStates, world-session, and match-state follow-up:

- Added immutable per-screen propagation policy to the existing `GameStates`
  engine. Events propagate top-to-bottom, variable/fixed updates propagate
  bottom-to-top, opaque screens can suppress underlay drawing, and screen-local
  timers advance only when their owner participates in the update pass.
- Added explicit single-instance ownership (`get`, `registered`, duplicate
  registration rejection) and deterministic idempotent close cleanup.
- Added `World.attach_session()`/`detach_session()`: an attached `Session` is
  polled exactly once by `world.update(dt)`, continues polling while simulation
  is paused, and closes with the World by default.
- Documented and strengthened the already implemented authoritative
  `ServerMatchState`/read-only `ClientMatchState` contract. Tests now directly
  prove a client match mirror cannot mutate a `NetworkVar`, while phase,
  revision, round, deadline, and late-join behavior remain covered.
- Focused state/performance run:
  `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_simple_state_machines.py
  tests/python/test_state_machine_performance.py` -> `16 passed in 0.32s`.
- Focused Pygame/session/match run after the new integration:
  `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_pygame_events.py
  tests/python/test_simple_state_machines.py
  tests/python/test_match_state.py` -> `26 passed in 0.65s`.
- Complete Python regression:
  `.venv\Scripts\python.exe -m pytest -q` -> `336 passed in 41.65s`.
- Configured strict typing:
  `.venv\Scripts\python.exe -m mypy` ->
  `Success: no issues found in 16 source files`.
- Dependency consistency:
  `.venv\Scripts\python.exe -m pip check` ->
  `No broken requirements found.`
- Added the maintained `docs/networking.md`, `docs/dedicated-servers.md`,
  `docs/network-security.md`, `docs/state-machines.md`, and
  `docs/game-states.md` references. Completion documentation remains open until
  the connection, benchmark, example, and final validation gates are finished.

Multiplayer example completion follow-up:

- Published all thirteen required public examples under `examples/networking`,
  with a single index that distinguishes twelve real-transport examples from
  the deterministic in-memory impairment simulator. Load/soak harnesses remain
  under `benchmarks` and tests rather than being presented as gameplay clients.
- Compiled all 27 Python source files with the active editable interpreter and
  invoked `--help` for all 22 executable entry points; every command exited 0.
- `.venv\Scripts\python.exe
  examples\networking\12_network_conditions\main.py` -> LAN 200/200/0,
  regional 200/199/1, adverse 200/194/6 delivered/lost with seed 53.
- `.venv\Scripts\python.exe
  examples\networking\03_listen_server\main.py --ticks 20` -> isolated local
  client and authority connected, exchanged both application messages,
  disconnected cleanly, and reported six lifecycle events.
- Added an automated example-manifest/syntax gate plus finite repeatability and
  real listen-exchange tests. Focused networking run:
  `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_network_examples.py tests/python/test_network_conditions.py
  tests/python/test_listen_server.py tests/python/test_session_process.py` ->
  `15 passed in 3.60s`.
- Interactive independent Pygame windows for the newly published 3D clients
  remain UNVERIFIED in this non-interactive run and are not claimed as passed.

Security and exception-cleanup follow-up:

- Audited each Phase 16 security category against targeted native/Python
  coverage. Malformed Session/RPC traffic, duplicate sequences, ownership,
  per-RPC rate limits, maximum connections, bounded queues/backpressure,
  handshake/peer timeout, reconnect churn, abrupt process loss, and shutdown
  cleanup all have direct assertions.
- Fixed `Session.host()` startup to be transactional when an application
  connection callback raises. The native listener is stopped, player state is
  cleared, the role returns to closed, and the original exception propagates.
  A regression reopens the same Session on the exact same port afterward.
- Security-focused command:
  `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_network_messages.py tests/python/test_network_rpc.py
  tests/python/test_network_transport.py tests/python/test_replication_resync.py
  tests/python/test_network_soak.py tests/python/test_two_process_network.py
  tests/python/test_server.py` -> `48 passed in 25.22s`.

Impairment and independent-process follow-up:

- Extended the retained two-process native transport sample with scoped
  `lan`, `regional`, and `adverse` GameNetworkingSockets impairment profiles.
  Server and client apply the profile independently inside their own OS
  processes and clear it before native shutdown.
- Added an adverse-profile independent-process acceptance test. Despite 100 ms
  configured one-way lag, 30 ms jitter, and 5% packet loss in both processes,
  the reliable request/reply completed and both peers exited cleanly.
- Added an explicit seeded unreliable-message reorder assertion. The native
  simulator delivered all 20 messages, used a non-send ordering, and reproduced
  the identical trace for the same seed.
- `.venv\Scripts\python.exe -m pytest -q
  tests/python/test_network_conditions.py
  tests/python/test_two_process_network.py` -> `13 passed in 23.76s`.

Capacity and prediction benchmark follow-up:

- Fixed the aggregate capacity command by running each 2/8/16/32-client count
  in a clean child process. This removes retained backend-worker/allocator state
  from the next count and makes RSS baselines comparable; the previous combined
  in-process command timed out during a final drain and remains recorded as a
  real failure rather than being hidden.
- Expanded `CapacityReport` with transport loss, queue rejection, event
  overflow, pending-byte peak, backpressure, full/delta snapshot counts, total
  snapshot bytes, and mean transform-frame size. The focused capacity gate ->
  `3 passed in 0.30s`.
- Full capacity command:
  `.venv\Scripts\python.exe benchmarks\network_capacity.py --ticks 120
  --warmup-ticks 20 --json` -> exit 0. Tick p99 was 0.718/3.627/14.488/
  38.908 ms for 2/8/16/32 clients; all final states were correct with zero
  loss, queue rejection, overflow, backpressure, or budget deferral. Mean
  transform frames were 64.85/64/64/64 bytes.
- The 32-client dense all-to-all run missed the 16.67 ms 60 Hz tick budget
  (25.415 ms median, 38.908 ms p99). This is reported as an unmet target, not a
  guaranteed capacity claim. Counts through 16 remained below budget at p99.
- Added `benchmarks/network_prediction.py`, using paired real native character
  motors, 60 Hz inputs, 20 corrections/client/second, and deterministic
  six-tick correction delay. Its focused gate -> `2 passed in 0.19s`.
- Full prediction command:
  `.venv\Scripts\python.exe benchmarks\network_prediction.py --ticks 120
  --warmup-ticks 20 --json` -> exit 0. All 2/8/16/32 runs converged exactly;
  each correction replayed 5.775 inputs on average, with p99 workload time
  0.266/0.903/1.573/3.497 ms respectively.

IPv6 transport follow-up:

- Confirmed the native Windows GameNetworkingSockets client/server already
  accepts numeric IPv6 and the native client suite exercises `::1`.
- Added `Session.host(local_address=...)` so an IPv6 listen host can connect
  its isolated local player over `::1` instead of the former fixed IPv4
  loopback address.
- Added a high-level real Session test binding `::1`, joining with the required
  bracketed `[::1]:port` syntax, completing the handshake, and delivering a
  named application message.
- `.venv\Scripts\python.exe -m pytest -q tests/python/test_session.py
  tests/python/test_network_transport.py` -> `24 passed in 0.40s`.
- IPv6 direct transport is verified on this host. UDP LAN discovery remains
  deliberately IPv4-only and no NAT/relay claim is implied.

Self-hosted signaling follow-up:

- Added `SignalingServer` and nonblocking `SignalingClient` over the existing
  native transport with a distinct protocol schema, 2 KiB bounded safe frames,
  numeric IPv4/IPv6 endpoints, 4–12-character normalized room codes, bounded
  directory capacity, connection ownership, explicit conflict/release events,
  and automatic disconnect cleanup.
- Added `RoomEndpoint`, `SignalingEvent`, `SignalingEventType`,
  `generate_room_code()`, and `normalize_room_code()` to `rix.net`.
- Added the headless `examples/networking/signaling.py` serve/register/resolve
  utility. It is a reference service outside the thirteen game examples.
- Real native loopback tests register, resolve, reject ownership/capacity
  conflicts, release, and prove a dropped host connection removes its room:
  `.venv\Scripts\python.exe -m pytest -q tests/python/test_signaling.py
  tests/python/test_session.py` -> `6 passed in 0.51s`.
- `.venv\Scripts\python.exe -m mypy` ->
  `Success: no issues found in 17 source files`.
- This completes the feasible self-hosted signaling backend, not a packet
  relay. It does not punch NAT, discover public addresses, authenticate public
  users, or make an unreachable direct endpoint reachable; documentation and
  examples make that boundary explicit.

Rollback-contract follow-up:

- Added `docs/rollback-contract.md` with the fixed-tick simulation boundary,
  canonical bounded snapshot/restore rules, registered ticked-input contract,
  stable digest requirement, deterministic random-state policy, irreversible
  side-effect deferral, resource bounds, and independent-process acceptance
  gates required before any future implementation can be public.
- Recorded ADR-0019 and synchronized architecture/API/networking references.
  No importable generic rollback API was added, and no deterministic claim is
  made for arbitrary Python, RIX scenes, or Jolt. The existing character motor
  correction/replay path remains explicitly narrower.

Final Phase 16 release and interactive follow-up:

- Updated the clean-wheel matrix to install the pinned Pygame CE 2.5.8 extra;
  the first CPython 3.11 attempt had failed collection with four missing-Pygame
  imports. The corrected matrix passed every supported interpreter.
- A real two-window authoritative-FPS run found and fixed pre-snapshot
  interpolation and `Vec3 + tuple` startup errors. A sweep found the same
  startup ordering issue in synchronized-cubes/cooperative/prediction examples;
  examples 07, 08, 10, and 11 then remained alive with empty stderr.
- Closing one FPS client initially disconnected its peer: a transform ACK
  already in flight referenced the just-despawned object. The authority now
  ignores ACKs for monotonically issued retired IDs while still rejecting
  never-issued IDs and future sequences. New transport and exact-example
  regressions prove the remaining peer stays connected with its local player.
- Final interactive Windows run: one headless server plus two independent
  Pygame CE 2.5.8/D3D11 clients visibly rendered `PLAYING`, health 100, and
  score 0. After one normal window close, the second remained connected,
  rendering, and at health 100. Both normal client closes had empty stderr.
- `.venv\Scripts\python.exe -m pytest -q` ->
  `352 passed in 53.28s`.
- `.venv\Scripts\python.exe -m mypy` ->
  `Success: no issues found in 17 source files`.
- `.venv\Scripts\python.exe -m pip check` ->
  `No broken requirements found.`
- Debug build/CTest -> `19/19 passed`, 1.20 seconds; Release build/CTest ->
  `19/19 passed`, 0.85 seconds.
- `scripts\build_wheel_matrix.ps1` clean-installed Pygame CE 2.5.8 and each
  wheel: CPython 3.11 `352 passed in 54.06s`; CPython 3.12 `352 passed in
  59.59s`; CPython 3.13 `352 passed in 52.83s`.
- Final wheel SHA-256: cp311
  `63c08746d6134a3599fa75ea0eb28266ddf63d347b5b4fe8839ee19f551172af`;
  cp312 `bca4a946fdcc674496ab67e6021779e2fd0a08bf761e701b5eba92d3163e89a2`;
  cp313 `6a818ea6d4ee0c7c3f0afa83b9f840aa7eaa1fd79cf4e270da4be84d9455edc4`.
- Published `docs/phase16-report.md` as the consolidated implementation,
  security, performance, validation, artifact, and limitation report.

## Phase 17 FBX and skeletal animation — initial audit/import checkpoint

- Preserved the existing modified/untracked beginner examples and root texture
  files; none were edited or deleted.
- Baseline `.venv\Scripts\python.exe -m pytest -q` -> `352 passed in 53.32s`.
- Baseline `ctest --test-dir build\windows-debug -C Debug
  --output-on-failure` -> `19/19 passed` in 2.13 s; Release -> `19/19 passed`
  in 1.97 s. The preceding commands without `-C` correctly reported all tests
  not run because these are multi-config trees; they were rerun correctly.
- `.venv\Scripts\python.exe -m pip check` -> `No broken requirements found.`
- `.venv\Scripts\python.exe -m mypy python` has 204 pre-existing errors in 17
  files. This broad command differs from the previously recorded focused
  17-file type gate and is tracked rather than attributed to FBX work.
- Located the mandatory assets in the adjacent RIX animation workspace and
  verified their hashes. Temporary repository copies used during development
  were later removed when the complete test was returned to that workspace.
- Pinned ufbx v0.23.1, added `.fbx` model-cache dispatch, binary/ASCII-capable
  loading, meter/Y-up conversion, polygon triangulation, multi-part materials,
  four normalized influences, shared skeleton construction, animation-only
  bone rigs, and baked shared TRS clips.
- MSVC Debug native build succeeded. The real-asset executable
  `build\windows-debug\Debug\easy3d_fbx_tests.exe` exits 0 and reports YBot
  55,320 triangles/52 deforming joints and Thriller one 18.8333 s clip/65
  joints, with all 52 target joints hierarchy-compatible and distinct sampled
  poses.
- GPU deformation, public playback/attachment, graphical YBot validation,
  embedded texture extraction, and performance results remain incomplete and
  are not claimed by this checkpoint.

## Phase 17 FBX and skeletal animation — completion evidence

- Added ufbx 0.23.1 at immutable commit
  `26a482ae66871d7de36eb722aa060bce95bce274`; binary and upstream ASCII
  fixtures pass. Real YBot/Thriller hashes, axes, units, clips, hierarchy,
  binds, media, and root delta are recorded in the external test project's
  `ASSET_AUDIT.md`.
- FBX now imports shared multi-part geometry/materials, coordinate and geometry
  transforms, skeleton clusters/binds, four normalized influences, and baked
  local TRS clips. glTF gained the same joint/weight vertex attributes without
  changing OBJ/static model behavior.
- Added automatic independent native controllers, loop/clamp/reverse,
  pause/resume/stop/restart, interruption-safe blending, exactly-once Python
  callbacks, compatible-rig rest correction, and explicit in-place/root-motion
  ownership. YBot's bind palette maximum identity error is `4.76837e-07`.
- Added D3D11 GPU skinning for position/normal/tangent material passes and
  directional/spot/point shadows. The public diagnostic reports `gpu` for the
  52-joint YBot. Rigs over 64 joints use bounded native CPU transient skinning;
  a generated 65-joint fixture reports `cpu` and rendered with an animated
  shadow pass.
- Added the typed `load_fbx`, `Model.add_animation`, `Model.play`, control/state,
  completion, root-motion, and skinning-diagnostic Python APIs plus stubs. The
  external `animation test/main.py` acceptance program uses only public APIs.
- Focused final commands:
  - `ctest --test-dir build\windows-debug -C Debug -R "rix\.(fbx|gltf)"
    --output-on-failure` -> `2/2 passed`.
  - `.venv\Scripts\python.exe -m pytest tests\python\test_fbx_animation.py -q`
    -> `6 passed in 0.61s`.
- Full gates:
  - `.venv\Scripts\python.exe -m pytest -q` -> `358 passed in 53.93s`.
  - `ctest --test-dir build\windows-debug -C Debug --output-on-failure` ->
    `20/20 passed` in 4.76 seconds.
  - `ctest --test-dir build\windows-release -C Release --output-on-failure` ->
    `20/20 passed` in 2.63 seconds after the complete optimized rebuild.
  - `.venv\Scripts\python.exe -m mypy` ->
    `Success: no issues found in 17 source files`.
  - `.venv\Scripts\python.exe -m pip check` ->
    `No broken requirements found.`
  - `python -m pip install -e ".[pygame,dev]"` built and installed the editable
    CPython 3.11 extension successfully.
- Clean wheel evidence:
  - `scripts\build_wheel_matrix.ps1 -SkipTests` built, clean-installed,
    dependency-checked, and native-import-smoked CPython 3.11/3.12/3.13 wheels.
  - SHA-256: cp311
    `f8e0dfc0873054701d5e1494482ddf2b3c00ca39a3ca4e10984e8a7f6138d8e9`;
    cp312 `8a2ec65bbd33ff8a7429349f01fe1ddaaaf868f4710c2b712de2a65c69ff0148`;
    cp313 `478c94e6bc597818bffce8a08814d5f675ed5cc2cfe3a47a06ce62b28a7db292`.
  - A separate clean cp311 wheel environment imported RIX and loaded the real
    YBot as version `0.1.0`, 55,320 triangles, 52 joints.
- The development benchmark on Ryzen 5 5600G / RTX 3070 Ti, D3D11, 960x540
  Ultra with shadows measured one/ten/100 real YBots at 0.345/1.211/
  138.415 ms average frame time and 6/42/402 draws. The 100-character case is
  not a 60 Hz capacity claim. A separate one-second generated 65-joint CPU-path
  run produced 1,479 frames and one shadow pass. The temporary repository
  benchmark harness was removed; historical results live in the external
  test project's `BENCHMARK.md`.
- After relocation, running external `animation test/main.py --seconds 2`
  exited 0 with 258 frames, `clip=Thriller`, time 1.433 seconds, and
  `skinning=gpu`. A final one-second repeat also exited 0 with 81 frames.
- Interactive Windows/D3D11 validation used the actual external test assets in
  standalone and Pygame-owned resizable windows. Multiple clearly distinct
  full-body Thriller poses retained correct YBot proportions, orientation,
  floor contact, scale, and alignment; the shadow changed with the limbs; a
  maximized resize rendered correctly; and both windows closed normally. An
  initial collapsed-mesh result was rejected and traced to FBX cluster bind
  spaces; the corrected palette and deformed bounds are covered by regression.
- Per the user-requested cleanup, repository copies of both FBX files, the
  duplicate `examples/animation` program, its bytecode, the temporary benchmark
  harness, and the two test-specific repository reports were removed. The
  working test, source assets, README, asset audit, and historical benchmark now
  live at `C:\Users\Ryan\Desktop\code\code\python\rix things\animation test`.
- Documented limitations are deliberate and visible: embedded/layered FBX
  texture fallback, unsupported advanced deformers/transparency, same-rig rather
  than semantic humanoid retargeting, four influences, 64-joint GPU limit,
  conservative animated culling, D3D11-only shader validation, and the measured
  100-character cost. Phase 17 is complete with no gameplay/network claims.

### Root-motion floor stability follow-up — 2026-11-08

- Root-motion extraction now transfers horizontal X/Z translation and yaw to
  the owner while keeping vertical hip translation and pitch/roll in the
  animated skeleton. Translation is also constrained to the world X/Z plane,
  preventing FBX loop-seam offsets or a tilted animated root from accumulating
  downward entity motion.
- `ctest --test-dir build\windows-debug -C Debug -R rix.fbx
  --output-on-failure` -> `1/1 passed` in 1.96 seconds.
- `C:\Users\Ryan\.venv\Scripts\python.exe -m pytest
  tests\python\test_fbx_animation.py -q` -> `6 passed in 0.83s`.
- A three-loop installed-extension diagnostic moved the owner 4.477534 units
  horizontally and reported `vertical_drift=0.000000000`.
- Rebuilt and reinstalled the editable CPython 3.11 RIX extension in
  `C:\Users\Ryan\.venv` successfully.
- A later embedded-animation `bg3.fbx` acceptance asset uses 66 joints and thus
  exercises the bounded CPU-skinning path. Its first shadow frame exposed a
  handle-0 collision that merged the plane transform into the CPU-skinned
  character batch. Static batching now excludes both CPU- and GPU-skinned
  batches. The exact external program remained running through ten seconds of
  D3D11 Ultra rendering with directional shadows and no exception; the
  verification process was then terminated manually.
- The external program was then changed to a 65-joint, 53,878-triangle
  `guy.fbx`, whose single expanded mesh exceeded bgfx's default transient pool.
  CPU skinning now uses a compact vertex layout, deforms each component/part
  once per frame, and reuses the allocation across all passes. RIX configures
  explicit 32 MiB vertex and 8 MiB index transient bounds. The exact updated
  program remained running for 20 seconds on D3D11 Medium without an exception
  and was then terminated manually. A non-editing Ultra override then remained
  running for another 20 seconds with directional shadows enabled, confirming
  that the same compact allocation was reused by shadow and main passes.
