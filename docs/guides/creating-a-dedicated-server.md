# Creating a Dedicated Server

A dedicated server is a separate headless process and is not a player:

```python
from rix import net

def joined(_server: net.Server, client: net.ConnectionId) -> None:
    print("joined", client.value)

def message(server: net.Server, event: net.NetworkEvent) -> None:
    server.send(event.connection, event.payload)

server = net.Server(
    port=7777,
    bind_address="0.0.0.0",
    max_players=16,
    tick_rate=60,
    on_connect=joined,
    on_message=message,
)

try:
    server.run()
except KeyboardInterrupt:
    server.stop("operator stopped")
```

No Pygame, SDL window, renderer, or GPU is initialized. Load a `Scene` before
`run()` only when authoritative scripts/Jolt physics are required. Callbacks run
on the thread that calls `poll()`, `step()`, or `run()`, never on a transport
worker thread.

Use registered prefabs and `ServerReplication` for spawning. Never accept a
Python class or import path from the network. The complete separate entry points
are `examples/networking/04_dedicated_server/server.py` and `client.py`.
