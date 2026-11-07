# RIX benchmark record

## 2026-11-05 — Pygame integration

Hardware: Windows x64, NVIDIA D3D11 `vendor=0x10de`, `device=0x2482`, Python
3.11.9, pygame-ce 2.5.8/SDL 2.32.10, 960x540 unless stated. Direct-mode FPS
below is CPU frame-submission throughput with vsync disabled; renderer GPU time
is the more meaningful device measure. Surface mode includes blocking readback,
Pygame blit, and flip. Values are short local samples, not cross-machine goals.

```powershell
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 1 --frames 30 --size 960 540
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 100 --frames 30 --size 960 540 --overlay
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 1000 --frames 20 --size 960 540
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 10000 --frames 10 --size 960 540
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode surface --objects 1 --frames 10 --size 320 180
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode surface --objects 100 --frames 10 --size 960 540
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode viewport --objects 100 --frames 20 --size 960 540 --viewport-size 256 256
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode viewport --objects 100 --frames 10 --size 960 540 --viewport-size 960 540
.venv\Scripts\python.exe benchmarks\pygame_integration.py --mode gpu --objects 0 --physics-bodies 200 --frames 60 --size 960 540
.venv\Scripts\python.exe benchmarks\render_cubes.py --count 1000 --seconds 2
```

| Mode | Scene | Mean submit/readback | Renderer GPU | Draws / instanced |
| --- | ---: | ---: | ---: | ---: |
| Pygame GPU | 1 cube | 0.175 ms | 0.930 ms | 3 / 0 |
| Pygame GPU + changing full overlay | 100 cubes | 30.504 ms | 31.519 ms | 4 / 1 |
| Pygame GPU | 1,000 cubes (779 visible) | 0.423 ms | 2.221 ms | 3 / 1 |
| Pygame GPU | 10,000 cubes (6,338 visible) | 2.739 ms | 4.169 ms | 3 / 1 |
| Surface 320x180 | 1 cube | 1.367 ms | unavailable after blocking readback | 2 / 0 |
| Surface 960x540 | 100 cubes | 8.867 ms | 0.009 ms reported pre-readback | 2 / 1 |
| Blocking Viewport 256x256 | 100 cubes | 0.859 ms mean / 1.171 ms p95 | 0.006 ms | 3 / 1 |
| Blocking Viewport 960x540 | 100 cubes | 3.127 ms mean / 3.353 ms p95 | 0.011 ms | 3 / 1 |
| Pygame GPU + fixed physics | 200 bodies | 0.209 ms render; 0.960 ms update mean / 2.473 ms p95 | 3.629 ms | 4 / 1 |
| Standalone GPU | 1,000 cubes | 0.345 ms median | 0.529 ms | 3 / 1 |

The explicit 512x512 RGBA Surface CPU copy averaged 0.89–1.05 ms. A changing
full-window overlay is costly because the current revision path regenerates
mips and replaces the GPU texture; update only when dirty. The standalone
1,000-cube run produced 3,842 frames in 2.070 s (1,856 FPS), used one instanced
draw, and ended at 108,077,056 bytes working set / 129,708,032 private bytes.

The Viewport rows intentionally use `blocking=True` to measure the worst-case
fresh-image path; normal subsequent refreshes are buffered and may return the
previous cached Surface instead of paying this stall. The 256x256 and 960x540
runs ended at 111,280,128 / 163,262,464 and 113,950,720 / 181,231,616 bytes
working-set/private memory respectively. The 200-body physics run ended at
144,998,400 / 207,466,496 bytes. These are process totals, not incremental
allocations attributable only to the measured feature.

RIX benchmarks cover local engine work only.

## 2026-11-06 multiplayer capacity and prediction

The capacity workload creates one real loopback native client per player and
replicates every authoritative transform to every client (dense all-to-all).
Each count runs in a fresh child process for an independent GameNetworkingSockets
runtime and RSS baseline. It is intentionally harsher than a spatially filtered
game and is not a player-count guarantee.

```powershell
.\.venv\Scripts\python.exe benchmarks\network_capacity.py --ticks 120 --warmup-ticks 20 --json
.\.venv\Scripts\python.exe benchmarks\network_prediction.py --ticks 120 --warmup-ticks 20 --json
```

| Clients | Tick median / p95 / p99 | Observe p95 | CPU | RSS peak | Server rate | Per client | Snapshot mean | Pending peak | Lost / rejected / overflow |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 0.221 / 0.641 / 0.718 ms | 2.988 ms | 42.7% | 33.5 MiB | 216.4 KiB/s | 108.2 KiB/s | 64.85 B | 209 B | 0 / 0 / 0 |
| 8 | 2.377 / 3.122 / 3.627 ms | 4.170 ms | 82.6% | 35.3 MiB | 1,392.8 KiB/s | 174.1 KiB/s | 64.00 B | 284 B | 0 / 0 / 0 |
| 16 | 7.077 / 11.658 / 14.488 ms | 12.728 ms | 88.8% | 39.3 MiB | 2,031.4 KiB/s | 127.0 KiB/s | 64.00 B | 270 B | 0 / 0 / 0 |
| 32 | 25.415 / 34.604 / 38.908 ms | 16.971 ms | 107.1% | 48.2 MiB | 2,428.0 KiB/s | 75.9 KiB/s | 64.00 B | 526 B | 0 / 0 / 0 |

All final replicated states were correct; no transform was budget-deferred or
backpressured. The 32-client dense workload exceeds the 16.67 ms budget for a
60 Hz simulation (25.415 ms median and 38.908 ms p99). The design target is
therefore not met for unfiltered 32-client all-to-all replication on this
machine; use spatial interest, lower snapshot frequency, and realistic
relevance sets. Counts through 16 remained below the budget at p99 in this run.

The prediction workload uses the actual native character motor in paired
headless client/server scenes. Every client submits one input per 60 Hz tick;
the authority emits corrections every three ticks (20/client/s), delivered
with a deterministic six-tick delay. The delayed suffix is genuinely replayed,
and the final correction must exactly converge position/velocity.

| Clients | Inputs | Corrections | Replays/correction | Error mean / max | Prediction tick median / p95 / p99 | Correct |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 2 | 240 | 80 | 5.775 | 0.7315 / 0.7600 | 0.056 / 0.226 / 0.266 ms | yes |
| 8 | 960 | 320 | 5.775 | 0.7315 / 0.7600 | 0.145 / 0.785 / 0.903 ms | yes |
| 16 | 1,920 | 640 | 5.775 | 0.7315 / 0.7600 | 0.263 / 1.535 / 1.573 ms | yes |
| 32 | 3,840 | 1,280 | 5.775 | 0.7315 / 0.7600 | 0.484 / 2.724 / 3.497 ms | yes |

These are short local Windows x64/CPython 3.11 measurements. Prediction error
is measured immediately before each deliberately delayed correction, not a
visible post-reconciliation error. CPU percentages can exceed 100% because the
native transport uses worker threads, and very short process-time samples have
coarse Windows accounting resolution.

## High-level construction

`benchmarks/high_level_api.py` compares convenience primitive construction with
equivalent explicit component construction:

```powershell
python benchmarks/high_level_api.py --objects 2000
```

The benchmark reports elapsed seconds and a convenience/explicit ratio. It is a
development signal, not a universal performance promise.

## Native geometry lifecycle

The CMake benchmark/lifecycle targets exercise repeated native geometry and
renderer-resource creation/destruction. Run them through the configured MSVC
build tree and record machine, build type, resolution, and driver with results.

## 2026-11-02 API simplification measurements

The Python 3.11 editable build ran on Windows x64 with a D3D11 NVIDIA device
(`vendor=0x10de`, `device=0x2482`) and the medium graphics preset.

| Workload | Before Phase 10 | After Phase 10 |
| --- | ---: | ---: |
| 2,000 high-level vs explicit objects | 0.095629 s / 0.091164 s (`1.049x`) | 0.087055 s / 0.085317 s (`1.020x`) |
| `native_add`, five warmed 5,000,000-call samples | 216.6 ns/call median | 205.0 ns/call median |
| 500 registered callbacks, 120 frames | 78.8 ns/callback median | 75.7 ns/callback median |
| 500 scripted entities, 120 frames | 8,713.2 ns/entity median | 7,979.0 ns/entity median |
| 200 physics bodies, 180 steps | 1,116.2 ns/body median | 1,028.2 ns/body median |

The controlled comparison loads the retained pre-change CPython 3.11 artifact
and current artifact under the same interpreter and machine conditions. The
earlier isolated 118.0/163.4 ns samples did not reproduce under that control;
they remain recorded in `docs/progress.md` but are not used for the gate.

The retained pre-change/current 2,000-cube samples created the scene in
0.065626/0.057327 seconds and reported median frame time 0.6524/0.6271 ms. Both
used 2 draw calls with 1 instanced scene call. Final working set was
108,605,440/104,198,144 bytes. These single three-second renderer samples favor
the current build but are development signals, not broad performance promises.

## Policy

Performance claims require a named workload, warmup, build configuration,
hardware, and exact command. Renderer frame counters and scheduler timing are
observable through the public diagnostics API.

## 2026-11-03 AutoTexture measurements

On the recorded Windows x64 / CPython 3.11 / NVIDIA D3D11 machine:

```powershell
.venv\Scripts\python.exe benchmarks\autotexture.py --objects 2000 --cache-loads 10000
```

Final-source result after filesystem-discovery coalescing: 2,000 shared textured
cubes in 900.284 ms (450.142 microseconds/object), first template generation in
6.537 ms, 10,000 cache loads at 131.352 microseconds/load, one unique cache
entry (`99.99%` measured hit rate), and one valid reload in 0.892 ms. The first
unoptimized sample was 2,413.051 ms (1,206.526 microseconds/object), so the
final path is 62.7% faster for this workload while retaining immediate
companion discovery.

The final bounded high-quality run reported 18 draw calls, one instanced draw,
0.095 ms backend CPU time, 5.556 ms GPU time, 20 GPU texture resources, and
2,946,376 bytes including mip chains. These are single-run development
measurements, not cross-device performance guarantees.

The D3D11 lifetime workload loaded 14 additional primitive/model map resources
(`3/1,398,108` to `17/2,113,524` count/bytes), cleared the scene, then returned
exactly to `3/1,398,108` after safe frames.

## 2026-11-03 advanced-lighting measurements

On the same CPython 3.11 / NVIDIA D3D11 device, the final bounded stress run was:

```powershell
.venv\Scripts\python.exe benchmarks\lighting.py --directional-lights 4 --point-lights 64 --spot-lights 32 --seconds 5 --preset ultra
```

It rendered 2,938 frames in 5.089 seconds (`577.28 FPS`) with all `4/64/32`
requested lights active, 122 visible instances, 6 total draw calls, 2 instanced
draw calls, 0.0368 ms reported backend CPU time, and 0.50176 ms reported GPU
time on the final frame. The four default-shadowed directional requests were
bounded to one active shadow caster/pass and 128 MiB at 4096x4096.

An overflow run requesting `6/70/36` admitted `4/64/32`, reported 12 culled or
budget-dropped lights, and rendered 974 frames in 2.098 seconds (`464.28 FPS`).
The Low preset admitted `1/4/2`, reported 21 dropped lights, allocated no
shadow memory, and rendered 501 frames in 1.091 seconds (`459.23 FPS`).

The established 2,000-cube regression workload remained at 3 draw calls/one
instanced scene call and rendered 4,142 frames in 5.114 seconds (`809.89 FPS`),
with 0.7698/2.057/3.0745 ms median/p95/p99 sampled frame times. This matches the
approximately 800 FPS immediate pre-lighting baseline rather than indicating a
material throughput loss for the ordinary one-directional-light case.

Sky texture replacement moved GPU texture telemetry from the fallback baseline
`3/1,398,108` count/bytes to panorama `4/12,582,920`, then cubemap
`4/7,689,564`, and returned exactly to baseline after disabling the sky.
Measurements are individual hardware-specific development samples, not
portable performance guarantees.
