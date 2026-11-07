# Advanced Engine APIs

The convenience layer does not replace explicit control. Advanced projects can:

- create/load/unload `Scene` objects and pass `scene=` everywhere;
- add/remove Collider, Rigidbody, renderer and character components;
- use native ray/shape/overlap queries and constraints;
- inspect renderer/scheduler statistics and diagnostics.

High- and low-level paths share the native scene, Jolt physics and retained
renderer state, so an application can mix them at deliberate ownership
boundaries. See `docs/api-contract.md` and `docs/architecture.md` for exact
invariants.
