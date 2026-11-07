# Deterministic rollback contract

RIX does not currently expose a lockstep or rollback runtime. This document is
the binding contract that any future implementation must satisfy before such a
feature can become public. It deliberately excludes ordinary RIX entities,
Python game objects, and Jolt worlds from an assumption of determinism.

## Simulation boundary

A rollback simulation must be an application-supplied, isolated deterministic
model with an interface equivalent to:

```python
class RollbackSimulation(Protocol[InputT]):
    @property
    def tick(self) -> int: ...

    def capture_state(self) -> bytes: ...
    def restore_state(self, tick: int, snapshot: bytes) -> None: ...
    def step(self, tick: int, inputs: Mapping[int, InputT]) -> None: ...
    def state_digest(self) -> bytes: ...
```

This is a specification, not an importable RIX class. A future API may choose
different names only if it preserves every invariant below.

## Required invariants

1. Ticks are non-negative integers on one declared fixed rate. Wall time,
   render frames, OS clocks, and transport arrival time cannot affect a step.
2. Inputs have a registered bounded schema, stable player identity, exact tick,
   and monotonic sequence. Missing-input policy is explicit (for example,
   neutral input or last-known input) and deterministic.
3. `capture_state()` returns a canonical, versioned, size-bounded byte string
   containing every value that can affect a future step. Object addresses,
   dictionaries with unstable iteration policy, file handles, random global
   state, and executable serialization are forbidden.
4. `restore_state(tick, snapshot)` replaces the complete simulation state. It
   cannot retain later caches, events, random state, subscriptions, or object
   identities that affect replay.
5. `step(tick, inputs)` consumes only the supplied state/input. Randomness uses
   snapshot-owned deterministic generators. Floating-point behavior must be
   demonstrated identical on every supported build or replaced with an agreed
   deterministic numeric representation.
6. `state_digest()` hashes the same canonical state used for snapshots. Digest
   mismatches are diagnostics/resynchronization signals, not silently ignored.
7. Audio, rendering, achievements, network sends, persistence, and other
   irreversible side effects are buffered by tick and committed only after the
   confirmation horizon. Replaying a tick cannot duplicate them.
8. History length, snapshot bytes, input bytes, replay steps per frame, player
   count, and resynchronization frequency are bounded before allocation.

## Required acceptance evidence

No rollback implementation may be advertised until tests prove all of these:

- two independent processes and every supported build produce identical
  digests for at least 10,000 ticks from the same snapshot/input stream;
- restoring multiple historical ticks and replaying to the present reproduces
  the original digest exactly;
- delayed, duplicate, reordered, missing, and maliciously oversized inputs are
  handled by the declared policy without unbounded work;
- divergence is detected and a bounded authoritative snapshot can resynchronize
  without executing arbitrary data;
- late input beyond the history window is rejected deterministically;
- replay never emits duplicate irreversible side effects;
- CPU, memory, snapshot size, replay count, and worst-case catch-up time are
  measured at supported player/history limits.

## Current boundary

`PredictedCharacterController` is not this system. It restores one supported
native character motor from authoritative corrections and replays only that
character's bounded unacknowledged input suffix. Dynamic Jolt physics, arbitrary
Python callbacks, ordinary `StateMachine` logic, and a whole RIX scene are not
claimed to be cross-process deterministic or rollback-safe.
