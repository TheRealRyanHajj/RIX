# Easy3D architecture

This document describes implemented architecture. Future systems remain governed
by `MASTERPLAN.md` and must not be inferred as available from this document.

## Scene and entity ownership

Each public Python `Scene` exclusively owns one native C++ `World`. A `World`
stores entities in reusable slots and is authoritative for entity lifetime and
native entity state. A Python `Entity` is a small reference containing:

- a strong reference to its owning Python `Scene`, so the native world cannot
  disappear while a live wrapper still needs to query it; and
- a native `EntityHandle` with `world_id`, slot `index`, and `generation`.

The numeric public `Entity.id` combines generation and slot index. It is unique
within a scene for the lifetime of that entity, but it is not a network identity
and must not be serialized as one. Networking will assign separate stable IDs.

Destroying an entity increments the slot generation before the slot is reused.
Clearing a scene increments every live slot generation. Native access validates
all three handle fields, so stale and cross-world handles cannot alias newly
created entities. `is_alive` is a non-throwing probe; other stale-handle access
raises native `InvalidEntityError`, exposed to Python as a `ReferenceError`
subclass.

Entity names, `enabled`, and `visible` are native slot data. Transform and
component storage will extend the same registry; they are not yet implemented.

## Scene activation and construction contexts

There is no implicit process-global scene. `Entity(scene=scene)` is explicit,
while `with scene:` uses a Python `ContextVar` to provide scoped construction
syntax that is safe across nested and asynchronous Python contexts. Leaving the
context restores the prior scene.

`Game.load_scene(scene)` establishes exclusive game ownership and activates the
scene. A scene cannot be loaded by two games simultaneously. Replacing or
unloading a scene deactivates it without deleting its entities; callers may opt
into clearing on unload. Closing a loaded scene is rejected.

## Threading status

Scene mutation is currently single-gameplay-thread state. The registry does not
claim concurrent mutation safety. Future worker, physics, and networking systems
must communicate through owned queues or synchronization boundaries instead of
mutating the world from uncontrolled threads.
