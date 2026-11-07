# Networking

`rix.net` is optional and uses the same native GameNetworkingSockets transport
for Pygame-only, Pygame+RIX, standalone, and headless programs. Importing it
does not create a window, renderer, scene, physics world, or Pygame object.

## Send a named message

```python
from rix import net

session = net.Session()
session.register_message("chat", text=str)

@session.on("chat")
def chat(sender: net.Player, *, text: str) -> None:
    print(sender.id, text)

session.join("127.0.0.1:7777")
session.send("chat", text="Hello")
session.update(1 / 60)
session.close()
```

Clients use `send()` to address their authority. A host must choose
`send_to(player, ...)` or `broadcast(...)`; server routing is never ambiguous.
Messages are reliable by default. Pass `unreliable=True` only for replaceable
state. `on("connect")` and `on("disconnect")` register lifecycle callbacks,
and `off(name, callback)` removes a handler.

The safe codec supports `None`, booleans, finite numbers, strings, bytes-like
values, lists/tuples, and dictionaries with string keys. It uses bounded UTF-8
JSON with tagged bytes—not pickle—and rejects malformed, oversized, deeply
nested, or schema-invalid frames.

## Host from the same machine

```python
host = net.Session()
host.host(port=7777, max_players=8)
```

This is a listen arrangement: it creates one authority and one separate local
client identity. A remote or dedicated client uses `join()`. It never starts an
authority implicitly.

Numeric IPv4 and IPv6 are supported by the native game transport. Bracket an
IPv6 address when including its port: `session.join("[::1]:7777")`. An IPv6
listen host must also choose an IPv6 address for its isolated local client:

```python
host.host(port=7777, bind_address="::", local_address="::1")
```

LAN discovery remains IPv4-only; IPv6 support here is direct transport, not
automatic discovery, DNS, NAT traversal, or a relay.

## Attach to a Pygame RIX world

```python
world.attach_session(session)

while world.running:
    dt = clock.tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)  # pumps the attached session exactly once
    world.render()
```

Networking still pumps while the world is paused. The default ownership closes
the session before the world releases the Pygame HWND. Use
`detach_session(session)` when returning to manual polling.

## Replication and authoritative state

`PrefabRegistry` is a local allow-list of prefab IDs, typed variables,
transforms, and RPC schemas. `ServerReplication` assigns object IDs and owns
spawns, despawns, values, ownership, snapshots, deltas, interest filtering, and
RPC validation. `ClientReplication` only constructs registered prefabs and
keeps client mirrors read-only.

The supported real-time prediction path is specifically
`PredictedCharacterController`. It sequences the native character motor's full
move/jump/sprint/crouch input, restores server corrections, and replays a
bounded unacknowledged suffix. It is not generic Python/Jolt rollback.

Shared match phase is explicit. Register `register_match_state()`, construct
`ServerMatchState` around the authority's spawned match object, and call
`advance(server.tick_count)` from server simulation. Clients construct
`ClientMatchState` only after synchronization. Local `GameStates` menus and
overlays remain local unless the application deliberately connects them to the
read-only match view.

See `docs/dedicated-servers.md` for headless deployment and
`docs/network-security.md` for trust boundaries and limits.

## Optional self-hosted room directory

`SignalingServer` is a functional headless reference directory over the same
native transport. A host holds a connection-scoped room registration and a
guest resolves the room asynchronously without blocking a Pygame loop:

```python
directory = net.SignalingClient()
directory.connect("127.0.0.1:7790")

for event in directory.poll():
    if event.type is net.SignalingEventType.CONNECTED:
        directory.resolve("PLAY-234")
    elif event.type is net.SignalingEventType.RESOLVED:
        assert event.endpoint is not None
        session.join(event.endpoint.connection_string)
```

Run the service with `net.SignalingServer(...).run()` or the reference utility
at `examples/networking/signaling.py`. Room codes and messages are bounded,
endpoints must be numeric IPv4/IPv6, registrations are owned by one connection,
and disconnects remove them automatically.

This is signaling, not relaying. It does not discover a public address, punch
NAT, open firewall ports, authenticate accounts, provide matchmaking, or carry
game traffic. A resolved endpoint still has to be directly reachable. Deploying
the unauthenticated reference directory on the public internet requires
application authentication, abuse controls, persistence, and monitoring.

## Rollback boundary

RIX does not expose generic rollback or lockstep. The explicit deterministic
snapshot/restore, input, side-effect, bounds, and acceptance requirements for a
future opt-in implementation are recorded in `docs/rollback-contract.md`.
Character prediction remains a narrower authoritative correction/replay path.
