# Dedicated servers

`rix.net.Server` is a native-transport, fixed-tick Python simulation host. It
does not create Pygame, SDL video, a window, bgfx, a renderer, or a GPU device.
The initial supported deployment platform is Windows x64; Linux has not been
validated and is not claimed.

## Smallest headless server

```python
from rix import net

def joined(server: net.Server, client: net.ConnectionId) -> None:
    print("connected", client.value)

def left(server: net.Server, event: net.NetworkEvent) -> None:
    print("disconnected", event.connection.value, event.reason)

server = net.Server(
    port=7777,
    max_players=16,
    tick_rate=60,
    on_connect=joined,
    on_disconnect=left,
)

try:
    server.run()
except KeyboardInterrupt:
    server.stop("console shutdown")
```

`run()` paces one authoritative fixed simulation and blocks until `stop()`.
`stop()` may be called from another Python thread. For embedding or tests,
`start()` binds without running, `poll()` only dispatches network events, and
`step()` pumps networking plus exactly one simulation tick.

Callbacks execute on the thread calling `run()`, `step()`, or `poll()`—never a
transport worker. `tick_count`, `connections`, `stats`, `scheduler_stats`, and
`script_errors` provide diagnostics.

## Optional authoritative scene and physics

```python
from rix import Scene, net

scene = Scene("server world")
server = net.Server(port=7777, tick_rate=60)
server.load_scene(scene)

try:
    server.run()
finally:
    server.stop()
    server.unload_scene(clear=True)
    scene.close()
```

The scene has scripts, fixed-step physics, entities, and character controllers
without rendering. The server is not a player. Every participant—including the
person who launched the process—connects through a separate `Client` or
`Session` process.

Use a shared `PrefabRegistry` schema with `ServerReplication` for registered
spawning and authoritative state. Never instantiate a class name supplied by a
client. `ServerMatchState` can advance waiting/countdown/playing/round-end/
match-end phases from `server.tick_count` and replicate its deadline to late
joiners.

## Independent client

```python
import pygame
import rix
from rix import net

pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
clock = pygame.time.Clock()
world = rix.World(screen)
session = net.Session()
session.join("127.0.0.1:7777")
world.attach_session(session)

try:
    while world.running:
        dt = clock.tick(60) / 1000
        for event in pygame.event.get():
            world.handle_event(event)
        world.update(dt)
        world.render()
finally:
    world.close()
    pygame.quit()
```

This client does not create an authority. Direct-IP joining requires a numeric
reachable address and an accessible UDP port. It does not provide NAT
traversal, hosted matchmaking, or a managed relay.
