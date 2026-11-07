# API simplification audit

Date: 2026-11-02

## Scope and evidence

This audit compares the implemented single-player RIX API with the
Pygame-level simplification goal. The authoritative inputs are `features.md`,
`docs/api-contract.md`, the Python package, native engine/window loop, tests,
benchmarks, and maintained beginner examples. Networking remains explicitly
outside the product.

The worktree already contains the intentional networking removal and the
beginner/gameplay additions recorded in `docs/progress.md`. Those changes are
preserved. No native subsystem needs replacement: the required simplification
can compose the existing renderer, scheduler, Jolt world, input map, audio
cache, retained UI, and gameplay utilities.

## Baseline commands and results

Run from `C:\Users\Ryan\Desktop\code\RIX` using the existing Python 3.11.9
editable environment:

```powershell
build\venv311\Scripts\python.exe -m pytest -q
```

Result: exit 0, `132 passed in 6.11s`.

```powershell
build\venv311\Scripts\python.exe -m mypy
```

Result: exit 0, `Success: no issues found in 2 source files`.

```powershell
build\venv311\Scripts\python.exe benchmarks\high_level_api.py --objects 2000
```

Result: exit 0,
`construction objects=2000 high=0.095629s explicit=0.091164s ratio=1.049`.

```powershell
build\venv311\Scripts\python.exe benchmarks\native_add.py --iterations 1000000
```

Result: exit 0,
`iterations=1000000 elapsed_seconds=0.117990 ns_per_call=118.0 final_value=500000`.

The prior fresh native Debug baseline remains 14/14 CTest targets passing as
recorded in `docs/progress.md`. It will be rerun after native loop changes.
Visible renderer benchmarking and interactive behavior have not been rerun for
this phase and are UNVERIFIED at this checkpoint.

## Current strengths to preserve

- `Game()` automatically creates a scene, camera, lights, input, audio, and a
  managed scheduler. `Game.run()` already drives callbacks, fixed physics,
  rendering, presentation, and cleanup on the window thread.
- `Cube`, `Sphere`, `Plane`, and `Model` already support simple transforms,
  colors, colliders, physics, textures, hierarchy, and explicit scenes.
- Entity `x/y/z` and `rx/ry/rz` properties are live native transforms.
- `Player` already binds movement, look, jump, sprint, crouch, camera, and the
  native character motor. `Enemy` already runs chase behavior through entity
  `fixed_update`, so it needs no parallel AI system.
- `Game.after()` and `Game.every()` already auto-run and return cancellable
  handles.
- Direct `Text`, `Button`, `Panel`, and `Sprite` construction already avoids
  manual HUD lookup. Row, Column, Grid, and Stack already implement active
  layout contexts and nested adoption.
- HealthBar and ScoreboardPanel already subscribe to source changes.
- Audio already caches decoded WAV files per `Game.audio` manager.

## Repetition and implementation leakage

| Task | Current calls | Required simplification |
|---|---|---|
| Manual loop | unavailable; native loop is monolithic | `while game.running: game.tick(60)` |
| Object motion | `move((x,y,z))`, `rotate((x,y,z))` | also accept three scalars |
| Raycast | pass `scene`, origin, direction, max distance | game/entity/player shortcuts |
| Raw input | `key_down`, `mouse_button_down`; `pressed` is action-only | `key`, `mouse`, and intuitive edge access |
| Mouse event | bind an action, then `on_input` | `@game.on_mouse("left")` |
| Health | construct `Health(entity, ...)` separately | `entity.add_health(...)` |
| Weapon | construct, aim, and call `advance(dt)` manually | player-owned, scheduler-advanced weapon |
| Sound | load then play through `game.audio` | cached `game.play_sound(path, ...)` |
| Tween | construct and advance manually | validated `entity.animate(...)` |
| Utility ownership | manual `advance/update` only | optional game/entity registration |

The largest leak is native loop ownership. SDL polling, window lifetime, frame
timing, callback execution, render submission, and presentation currently live
inside one blocking `run_window_loop`. Manual stepping must refactor that loop
into a persistent native session; recreating the window per tick or creating a
second Python simulation path would violate lifecycle and scheduler invariants.

## Required loop contract

Both `run()` and `tick()` will call one native frame-step path in this order:

1. calculate elapsed steady-clock time;
2. begin input edge collection and pump SDL events;
3. apply focus, pointer-lock, gamepad, and resize changes;
4. finalize the frame's input snapshot;
5. invoke the one Python frame callback on the window/gameplay thread;
6. advance the existing scheduler, including bounded fixed steps, physics,
   entity callbacks, collision delivery, timers, and variable/late updates;
7. update the audio listener;
8. render and present exactly once;
9. publish renderer/frame counters and apply the selected frame limit.

In the simple manual example, code after `tick()` changes state for the next
presented frame. Managed callbacks run inside step 6 and affect the current
frame. No fixed simulation work may be exposed as a second public advance.

## Compatibility and risk controls

- Existing root exports and explicit submodule APIs remain callable.
- Convenience health, weapons, timers, state machines, audio, and tweens must
  delegate to their existing implementations, not create duplicate state.
- Dynamic rigid-body transforms continue to require physics operations rather
  than unsafe direct movement.
- A persistent manual native session must be closed deterministically by the
  context manager and must reject concurrent `run`, recursive `tick`, and
  cross-thread callbacks.
- Tests need controllable clocks or a test seam; timing assertions must not
  depend on desktop scheduling.
- Interactive D3D11, input feel, speaker output, and visible ordering remain
  hardware checks and cannot be inferred from unit tests.

## Implementation order

1. Refactor one native window session and expose `Game.running/tick`.
2. Add pure-Python movement, raycast, input, mouse, and collision adapters.
3. Add managed ownership for health, weapons, utilities, sound, and tweens.
4. Curate modules without removing compatibility exports.
5. Add required examples and learning-path documentation.
6. Run the full native/Python/type/performance/interactive validation matrix
   and update all public contracts with actual evidence.

## Completion audit

The implementation was audited against Phases A–K after the final input fix.
Evidence is current source plus the exact runs in `docs/progress.md`.

| Requirement group | Authoritative evidence | Result |
| --- | --- | --- |
| Shared managed/manual loop | One native `WindowSession`; manual-loop unit/native/desktop checks; documented frame order | Achieved |
| Loop safety and one scheduler | Recursive/concurrent/exception/stop/context tests; 120 ticks produced 120 frames; physics single-step test | Achieved |
| Beginner package and objects | Root compatibility audit, curated modules, constructor/movement/hierarchy tests | Achieved |
| Raycast, input, and collision shortcuts | Beginner API, native input-edge, physics query/event, and desktop Escape tests | Achieved |
| Managed health, weapon, enemy, timers, state, tween, animation | Gameplay/utility lifecycle tests including scene replacement and entity destruction | Achieved |
| UI and binding | Row/Column/Grid/Stack tests, health/score binding tests, visible Play/Quit interaction | Achieved |
| Audio | Cache/playback/control tests, one-call API test, SDL3 device and voice examples | Achieved; speaker audibility remains a stated sensory limit |
| Learning path and examples | Seven required examples executed; 14 ordered guides; all repository examples swept | Achieved |
| Compatibility and typing | Explicit low-level suites, `143` tests on CPython 3.11–3.13, mypy and stubtest | Achieved |
| Native and distribution | CTest 14/14, editable install, three clean wheel installs and content audit | Achieved |
| Performance | Controlled pre/current construction, callback, traversal, physics, renderer, memory, and draw-call comparisons | Achieved; no material regression observed |
| Real Windows desktop | D3D11 render, managed/manual loops, resize, input, physics scene, retained UI, close, repeated lifecycle | Achieved on the recorded NVIDIA machine |

No networking, multiplayer, server, replication, matchmaking, RPC, or
prediction abstraction was reintroduced.
