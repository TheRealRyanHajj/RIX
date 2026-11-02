# Easy3D benchmark record

Benchmark numbers describe the named workload and machine only. They are not
general game, Internet, or hardware guarantees.

## Phase 5.6 network capacity workload

Run the post-baseline gate after an editable install:

```powershell
python benchmarks/network_capacity.py --ticks 120 --warmup-ticks 20 --enforce-budget
```

The finite real-GameNetworkingSockets loopback workload creates 8, 16, then 32
independent client connections in one Python process. The authority owns one
moving transform and one integer `NetworkVar` per client. Every tick changes
every transform and fans it out to every client; every thirtieth tick also
changes and flushes every variable. Initial snapshots and a complete unmeasured
transform frame establish per-connection delta baselines. The measured loop
then validates final sequence, position, variable value, object count, zero
application-budget deferrals, process CPU/RSS, transport application bytes and
one stable latency sentinel per connection. It runs as fast as the process can
with a 0.5 ms worker scheduling yield; it is not a paced 60 Hz simulation.

Recorded machine on 2026-11-01:

- Windows 11 Home 64-bit, version 10.0.26200
- AMD Ryzen 5 5600G, 6 cores / 12 logical processors, reported max 3901 MHz
- 34,227,388,416 bytes installed physical memory
- CPython 3.11 x64 from `build/venv311`
- loopback only; no external network or rendered GPU workload

The first correct 120-tick baseline identified repeated delta reconstruction,
quaternion normalization, per-object reliable ACK sends, and benchmark history
inspection as hot work. It measured 32-client median/p95/p99 tick cost
47.014/59.397/68.719 ms, 133.5% process CPU, 100.4 MiB peak RSS, 35.851 ms
observation p95, and zero deferred frames. The implementation now caches
identical immutable-baseline delta results per flush, computes quaternion
length once, coalesces up to 256 replaceable ACKs per client datagram, and
samples one latency sentinel without weakening final all-object correctness.

Post-baseline budgets are deliberately above observed variance:

| Gate | Limit |
|---|---:|
| final state | correct |
| transform budget deferrals | 0 |
| aggregate measured-loop tick p99 | 100 ms |
| sentinel observation latency p95 | 50 ms |
| process CPU | 200% (two logical-core equivalents) |
| process peak working set | 128 MiB |
| authority application bytes per measured tick | 80 KiB |

Final enforced run:

| Clients | median / p95 / p99 / max tick ms | CPU | peak RSS | authority rate | per-client rate | latency p95 | Correct/deferred |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 4.271 / 6.044 / 6.845 / 7.398 | 78.7% | 32.3 MiB | 840.9 KiB/s | 105.1 KiB/s | 8.570 ms | yes / 0 |
| 16 | 13.875 / 17.090 / 17.685 / 20.074 | 103.6% | 40.2 MiB | 1153.8 KiB/s | 72.1 KiB/s | 9.528 ms | yes / 0 |
| 32 | 49.270 / 64.640 / 66.447 / 77.815 | 112.9% | 55.1 MiB | 1288.2 KiB/s | 40.3 KiB/s | 29.067 ms | yes / 0 |

`bytes_sent`/`bytes_received` are GameNetworkingSockets application payload
counters, not Ethernet/IP/UDP/encryption overhead. Tick time includes the
authority plus every in-process client poll and therefore does not represent a
dedicated server-only tick. The dense 32×32 transform fan-out is within the
declared gate but does not sustain 60 aggregate loops per second on this
machine; games needing that cadence must use interest filtering, lower network
snapshot frequency, fewer relevant objects, or native/batched gameplay state.

## Phase 5.7 adverse lifecycle soak

```powershell
python benchmarks/network_soak.py --clients 4 --cycles 10 --inputs-per-client 64 --profile adverse
```

The finite run uses the declared adverse backend impairment (100 ms one-way
lag, 30 ms jitter, 5% fake-send loss) while sending reliable owner-gated RPC
input bursts above a 16-call/second authority limit. Each cycle requires every
reliable call to reach the authority, disconnects one rotating client, observes
reliable despawn on every remaining replica, reconnects it, and requires a
complete fresh snapshot plus assignment. Impairment is then reset before an
explicit whole-server shutdown, and every client must observe disconnect and
clear its mirror. This separation tests loss recovery and deterministic clean
shutdown without turning a deliberately dropped close packet into a peer-
timeout benchmark.

The recorded run sent and received all 2,560 input RPCs, executed 640 within
the authority rate limits, dropped 1,920 at the application rate limiter,
completed 10 reconnects, observed all 14 authority disconnects (10 rotating +
4 shutdown) and all 4 client shutdowns, and finished correct in 35.152 seconds.
This is local finite stress evidence, not a duration, WAN, or production-load
guarantee.

## Phase 6.8 final regression and optimization

The final gate reused the recorded Windows 11/Ryzen 5 5600G/CPython 3.11 host
and fixed Phase 5 budgets. A first full capacity run failed rather than being
accepted or hidden:

| Clients | median / p95 / p99 / max tick ms | CPU | peak RSS | latency p95 | Correct/deferred |
|---:|---:|---:|---:|---:|---:|
| 8 | 7.564 / 11.784 / 16.214 / 20.751 | 89.0% | 34.4 MiB | 13.903 ms | yes / 0 |
| 16 | 24.284 / 33.291 / 35.712 / 41.800 | 94.5% | 39.4 MiB | 15.774 ms | yes / 0 |
| 32 | 92.980 / 123.318 / **132.676** / 202.321 | 98.6% | 58.1 MiB | **62.088 ms** | yes / 0 |

The 32-client p99 and latency exceeded the unchanged 100/50 ms budgets.
Repeated isolated runs still failed. A 60-tick cProfile sample reported
20,175,538 calls in 14.861 seconds, including 5.853 seconds in server
`flush_transforms`, 30,285 delta reconstructions and 6.806 seconds in client
frame application.

Two measured corrections were made:

1. The per-flush server delta cache now keys on baseline sequence and every
   immutable component rather than Python object identity. Packet timing can
   produce separate snapshot objects with identical values; the former key
   permanently fragmented reuse. The next profile fell to 15,423,568 calls and
   2.771 seconds in `flush_transforms`.
2. Internal transform wire decode now constructs `Vec3`/normalized `Quat`
   values through private bounded helpers after frame length, finite values,
   integer quantization and the prior baseline are already validated. Public
   math constructors retain all type/finite validation. This removes redundant
   iterable conversion and component validation for every received replica
   while preserving zero-quaternion and zero-scale rejection.

Final enforced capacity run, with every original budget unchanged:

| Clients | median / p95 / p99 / max tick ms | CPU | peak RSS | authority rate | per-client rate | latency p95 | Correct/deferred |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 4.078 / 6.135 / 8.263 / 8.744 | 67.8% | 33.4 MiB | 835.1 KiB/s | 104.4 KiB/s | 8.607 ms | yes / 0 |
| 16 | 13.438 / 20.315 / 26.944 / 44.841 | 98.9% | 38.0 MiB | 1173.1 KiB/s | 73.3 KiB/s | 16.972 ms | yes / 0 |
| 32 | 49.899 / 70.131 / 88.847 / 111.698 | 107.5% | 49.6 MiB | 1238.1 KiB/s | 38.7 KiB/s | 34.021 ms | yes / 0 |

The final Phase 5 adverse workload also passed in 33.493 seconds: 2,560/2,560
reliable inputs received, 654 executed, 1,906 application-rate-limited, 10
reconnects, 14 authority disconnect observations, 4 client shutdowns and
correct final state. Different executed/limited counts from the earlier run are
expected because the one-second rate-limit windows and jitter boundary are
time-based; their sum and reliable delivery remain exact.

The Release C++ loop benchmark completed 10,000,000 iterations in 0.025454
seconds. One million Python-to-native `native_add` calls took 0.363130 seconds
(363.1 ns/call) on this run.

The GUI D3D11 10,000-cube workload ran for 10.081 seconds and produced 2,222
frames (220.4 overall FPS). Its sampled frame median/p95/p99 were
3.939/5.676/10.304 ms. The final frame submitted two draw calls: one instanced
draw containing 9,318 visible cubes, with 682 culled. Working set was 28.8 MiB
before creation, 32.1 MiB after creation, 83.2 MiB after the run and 132.8 MiB
peak. These figures are workload/machine evidence, not a general FPS or memory
guarantee; no human screenshot/appearance review accompanied the timed run.

