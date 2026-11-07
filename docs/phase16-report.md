# Phase 16 completion report

Status: implemented and verified on Windows x64 on 2026-11-06. This report is
evidence for the multiplayer and state-system milestone; it is not a claim of
hosted internet infrastructure, generic rollback, Linux support, or performance
on hardware other than the recorded machine.

## Delivered systems

- One optional GameNetworkingSockets 1.6.1 transport serves Pygame-only,
  Pygame+RIX, standalone, and headless programs. It provides reliable and
  unreliable delivery, bounded queues/messages, lifecycle events, statistics,
  protocol/schema handshakes, numeric IPv4/IPv6 direct connections, and an
  IPv4 LAN-discovery layer.
- `rix.net.Session` provides safe named JSON messages, typed field schemas,
  player identities, explicit client/server/broadcast routing, listen hosting,
  and gameplay-thread callbacks. It never uses pickle or executes received
  Python objects.
- `Server` and `Client` support independent headless authority and client
  processes. `World.attach_session()` provides exactly-once integration with a
  Pygame-owned loop without making graphics a networking dependency.
- Registered prefabs, stable object IDs, typed `NetworkVar` values, spawn/
  despawn, ownership, snapshots, deltas, late joins, bounded resynchronization,
  transform interpolation, spatial interest, budgets, and telemetry provide
  replicated state.
- Registered RPCs enforce direction, schemas, sequence checks, ownership,
  limits, and authority. `PredictedCharacterController` provides the supported
  native-motor prediction/reconciliation path; it is not generic rollback.
- `SignalingServer` and `SignalingClient` implement a self-hosted room-code
  endpoint directory. They do not relay packets or traverse NAT.
- `StateMachine` supports beginner decorators, explicit legacy registration,
  guarded/prioritized transitions, enter/exit callbacks, timers, pause/reset,
  bounded reentrancy, entity ownership, and lifecycle cleanup.
- `GameStates` supports Pygame event/update/fixed-update/draw forwarding,
  deferred transitions, overlays, propagation policies, timers, and ownership.
  Server-authoritative match states remain separate from local menus and
  overlays.

The complete call-by-call public catalog is in `features.md`; architecture,
trust boundaries, and tutorials are linked from `docs/networking.md` and
`docs/guides/README.md`.

## Examples

`examples/networking` contains all thirteen required examples, from Tic-Tac-Toe
and chat through synchronized 3D, cooperative play, authoritative FPS rules,
prediction, and deterministic impairment. `examples/states` contains all ten
required state/screen/server examples. Benchmark and load clients remain under
`benchmarks` and `tests`, not public gameplay examples.

A final runtime sweep kept examples 07, 08, 10, and 11 alive for four seconds
with independent server/client processes and empty stderr. The sweep found and
fixed stale pre-snapshot interpolation calls and tuple/`Vec3` arithmetic.

The authoritative FPS validation used one hidden headless server and two
independent visible Pygame CE 2.5.8 clients. Both rendered the shared `PLAYING`
state with health 100. Closing one window left the other connected, rendering,
and at health 100; both normal window-close paths produced empty stderr. This
run exposed and fixed a real delayed-transform-ACK/despawn race. A permanent
two-client regression now proves that a departing peer cannot disconnect or
erase the remaining client's local player. Held-key movement feel was not
manually judged by the UI automation; movement/RPC/prediction input paths are
covered by automated tests.

## Security result

The focused security suite covers malformed and oversized traffic, schema and
protocol mismatch, replay/sequence checks, RPC direction/ownership/rate limits,
connection limits, queue/backpressure behavior, timeouts, reconnects, abrupt
process loss, and exception cleanup. Session startup is transactional when an
application callback raises. Delayed ACKs for a monotonically allocated but
already retired transform are now ignored as a harmless race; never-issued IDs
and future sequences still fail closed.

See `docs/network-security.md` for the threat model. Transport encryption is
the protection supplied by GameNetworkingSockets; RIX does not claim user
authentication, anti-cheat, a public relay, or production service hardening.

## Performance result

The recorded 120-tick dense replication benchmark produced these server tick
p99 values:

| Clients | Tick p99 | 60 Hz budget result |
| ---: | ---: | --- |
| 2 | 0.718 ms | within budget |
| 8 | 3.627 ms | within budget |
| 16 | 14.488 ms | within budget |
| 32 | 38.908 ms | exceeds budget |

All final states were correct and the run reported zero loss, queue rejection,
event overflow, transform backpressure, or budget deferral. The paired native
prediction benchmark converged exactly at 2/8/16/32 clients with p99 workload
times of 0.266/0.903/1.573/3.497 ms. These are local measurements, not capacity
guarantees. Full details are in `docs/benchmarks.md`.

## Final validation

- Debug native build/CTest: 19/19 passed in 1.20 seconds.
- Release native build/CTest: 19/19 passed in 0.85 seconds.
- Editable CPython 3.11 suite: 352 passed in 53.28 seconds.
- Strict mypy: no issues in 17 source files.
- `pip check`: no broken requirements.
- CPython 3.11 wheel: 352 passed in 54.06 seconds.
- CPython 3.12 wheel: 352 passed in 59.59 seconds.
- CPython 3.13 wheel: 352 passed in 52.83 seconds.

Final Windows wheel SHA-256 values:

```text
63c08746d6134a3599fa75ea0eb28266ddf63d347b5b4fe8839ee19f551172af  rix-0.1.0-cp311-cp311-win_amd64.whl
bca4a946fdcc674496ab67e6021779e2fd0a08bf761e701b5eba92d3163e89a2  rix-0.1.0-cp312-cp312-win_amd64.whl
6a818ea6d4ee0c7c3f0afa83b9f840aa7eaa1fd79cf4e270da4be84d9455edc4  rix-0.1.0-cp313-cp313-win_amd64.whl
```

## Remaining limits and next steps

- Validate direct internet play on multiple physical networks and hardware.
- Add a production-authenticated signaling deployment and packet relay only if
  the product needs connectivity for hosts behind NAT.
- Profile or redesign the dense 32-client case before advertising 60 Hz at
  that load.
- Implement generic rollback only against the contract in
  `docs/rollback-contract.md`; arbitrary Python/Jolt state is not deterministic.
- Validate Linux headless builds separately before claiming Linux support.
- Manually judge multiplayer held-key movement, mouse feel, audio, and device
  behavior on the target game's actual hardware.
