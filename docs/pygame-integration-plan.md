# RIX and Pygame Community Edition integration plan

## Audit baseline

Audit date: 2026-11-05 on Windows x64, Python 3.11.9, CMake 4.0.1,
Ninja 1.12.1, and the installed Visual Studio 18 Build Tools toolchain.

The current RIX implementation is a C++20 engine with a pybind11 package,
SDL3-owned standalone window, bgfx D3D11 renderer, Jolt world, native scene and
entity storage, typed Python convenience layer, assets, material maps, bounded
multi-light/shadow rendering, skyboxes, UI, audio, input, scheduling, and
standalone managed/manual loops. The repository begins this phase with a large
intentional dirty tree containing the completed networking removal and later
engine work; that work must be preserved.

The verified pre-migration baseline is:

- `tests/python`: 200 passed in 16.33 seconds.
- Debug CTest: 14/14 passed in 2.70 seconds.
- Release CTest: 14/14 passed in 1.27 seconds.
- strict mypy target and `pip check`: passed.
- `import rix`: version 0.1.0 loaded from the editable checkout.

Pygame CE was not installed in the baseline environment. `pip index versions
pygame-ce` reports 2.5.8 as the current stable package, which will be the pinned
optional integration dependency.

## Reusable systems

The native Scene, entity handles, transforms, camera, meshes, materials,
textures, model loaders, lights, shadows, skyboxes, renderer scene traversal,
Jolt physics, fixed stepping, queries, gameplay callbacks, and statistics are
display-adapter independent and should remain authoritative. Existing Python
objects should be moved mechanically to `rix`, not reimplemented.

Standalone `Game.run()` and `Game.tick()` remain the SDL3-owned adapter. The
same Scene and fixed scheduler will be used by the Pygame-owned adapter.

## Components requiring adaptation

1. Split `WindowSession` responsibilities into standalone window/event/audio
   ownership and a renderer session that can target a validated external HWND.
2. Add an externally stepped native frame path with caller-supplied seconds,
   no sleep, no SDL event polling, and no duplicate physics advancement.
3. Add Python translation for actual Pygame event objects without importing
   Pygame unless the integration API is used.
4. Add owned RGBA texture bytes and explicit texture updates. Surface memory
   is copied before native/GPU submission; native resources never borrow a
   Surface pointer.
5. Add offscreen targets and measured readback before exposing `Viewport`.
6. Move the authoritative Python package to `rix._rix`; retain `easy3d` only as
   a warning compatibility facade over the same modules/native singleton.

## Pygame CE and graphics risks

Pygame CE 2.5.8 uses SDL2 (minimum SDL 2.0.20), while standalone RIX embeds a
private static SDL3. The two runtimes must never both own, pump, resize, or
destroy the same SDL window. Pygame's documented `display.get_wm_info()` returns
the platform window identifier, but an HWND alone does not prove safe concurrent
presentation.

bgfx requires platform data before initialization and treats its `nwh` as the
native swap-chain window. bgfx is process-global in this engine, so only one
active renderer session is supported initially. Initialization, render calls,
resize, readback completion, and shutdown remain on the creating thread.

High-DPI logical size and drawable pixel size can differ. The adapter receives
both explicitly and treats renderer dimensions as pixels. Pygame resize/focus
events are the only event authority in integrated mode.

## Rendering prototypes and decision gate

### Mode A: GPU-composited external window

Pygame creates the ordinary resizable display and exports its Win32 HWND. RIX
validates `IsWindow`, creates the bgfx D3D11 swap chain on that HWND, renders the
3D scene, composites an optional uploaded Pygame RGBA overlay, and performs the
only presentation. Once attached, application code must not call
`pygame.display.flip()` or `pygame.display.update()` for that display. Pygame 2D
drawing targets a separate alpha Surface supplied to RIX explicitly.

This is the preferred full-window path only if an actual Windows desktop test
proves creation, repeated render, resize, focus, overlay alpha, shutdown, and
reattachment without SDL2/D3D11 corruption.

### Mode B: Surface compatibility

RIX renders into an offscreen GPU framebuffer, post-processes into RGBA8, blits
into a texture created with `BGFX_TEXTURE_READ_BACK`, and requests a bgfx read.
Pygame remains the sole presentation owner and may freely blit/flip.
Full-window compatibility output is synchronous. Viewports use independent
camera/size targets and request-owned staging/pixel storage: the first default
image blocks, later refreshes poll a bounded buffered queue and reuse cached
output until bgfx's documented completion frame is reached.

This is the reliable compatibility path for embedded or multiple viewports and
existing software-display projects. It is expected to be slower because of the
GPU-to-CPU copy and Pygame blit.

### Gate

The gate passed on the recorded NVIDIA D3D11 machine (`vendor=0x10de`,
`device=0x2482`). The Pygame CE 2.5.8 HWND prototype rendered, resized from
640x360 to 800x450 without changing HWND, and shut down cleanly. The public
adapter subsequently passed direct overlay/Surface texture rendering and a
320x180 offscreen readback measured at 11.764 ms for one sample. These are
hardware-specific correctness measurements, not universal performance claims.

## Proposed public contracts

```python
import pygame
import rix

screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
world = rix.World(screen, mode="gpu")

for event in pygame.event.get():
    world.handle_event(event)

world.update(dt)               # seconds; fixed physics remains internal
world.set_overlay(hud)         # one explicit Pygame Surface upload
world.render()                 # RIX presents in GPU mode
world.close()
```

Surface mode uses `frame = world.render()` or
`Viewport(world, size=..., camera=...).to_surface()` and leaves
`pygame.display.flip()` to the application. Viewports have independent camera
copies and exact render sizes. `World.update(dt)` clamps large
deltas, bounds catch-up steps, and never sleeps. `handle_event()` consumes only
the supplied object and never drains Pygame's queue. Pygame polling APIs remain
usable.

Primitives initially accept either `scene=world.scene` or the Pygame-oriented
first positional `world`; only one canonical constructor path will remain after
compatibility testing. RIX `Vec2`/`Vec3` conversion accepts finite iterable or
attribute-based Pygame vectors. `pygame.Rect` conversion is limited to pixel
viewport/overlay APIs.

## Package migration

- Distribution: `rix`, version history retained from 0.1.0.
- Authoritative package/native extension: `rix` and `rix._rix`.
- Compatibility package: `easy3d`, emitting `DeprecationWarning` and forwarding
  to the same RIX Python objects and native extension.
- Optional extra: `pygame = ["pygame-ce==2.5.8"]`.
- First-party tests, examples, benchmarks, messages, and documentation migrate
  to RIX. Internal C++ namespace/include paths may remain `easy3d` during this
  phase to avoid a high-risk engine-wide source rewrite.

## Test and benchmark plan

Automated gates cover package identity/shim behavior, dependency absence and CE
version checks, HWND validation, ownership/state errors, caller-supplied delta
clamping and fixed-step counts, event mappings, vector/Rect conversion, exact
RGBA channel/alpha/pitch conversion, copied lifetime, explicit updates,
readback byte counts, viewport sizes, cleanup, and standalone regression.

Benchmarks record hardware and compare one/100/1,000/10,000 objects for
standalone, external GPU, and Surface modes; overlay upload and small/full-size
readback are measured separately. Interactive results are recorded only after a
visible Windows run.

## Dependency and ownership policy

Pygame CE is LGPL-2.1-or-later and remains a separately installed optional
Python dependency. RIX neither vendors nor statically links it. Standalone RIX
continues to own SDL3 video/audio. In Pygame mode, Pygame owns window, events,
and default audio; native RIX audio is opt-in and does not initialize by default.

Official references:

- <https://pyga.me/docs/ref/display.html#pygame.display.get_wm_info>
- <https://pyga.me/docs/ref/pygame.html#pygame.get_sdl_version>
- <https://github.com/pygame-community/pygame-ce>
- <https://bkaradzic.github.io/bgfx/bgfx.html#platform-specific>
- <https://bkaradzic.github.io/bgfx/bgfx.html#_CPPv4N4bgfx11readTextureE13TextureHandlePv8uint16_t7uint8_t>

