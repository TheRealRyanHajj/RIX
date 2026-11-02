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

