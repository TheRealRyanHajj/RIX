# Sending a Network Message

Use `Session` when you only need named application messages. It does not create
Pygame, a window, a scene, physics, or replication.

Start a host:

```python
import time
from rix import net

session = net.Session()
session.register_message("chat", text=str)

@session.on("chat")
def chat(sender: net.Player, *, text: str) -> None:
    print(sender.id, text)

session.host(port=7777, bind_address="127.0.0.1")
try:
    while session.is_open:
        session.update(1 / 60)
        time.sleep(1 / 60)
finally:
    session.close()
```

In another process, join and send:

```python
import time
from rix import net

session = net.Session()
session.register_message("chat", text=str)

@session.on("connect")
def connected(_server: net.Player) -> None:
    session.send("chat", text="Hello from another process")

session.join("127.0.0.1:7777")
try:
    while session.is_open:
        session.update(1 / 60)
        time.sleep(1 / 60)
finally:
    session.close()
```

Messages are reliable by default. Use `unreliable=True` only for replaceable
updates. Hosts route deliberately with `send_to()` or `broadcast()`. Schemas
reject missing, extra, or wrongly typed fields; the safe codec never uses
pickle. The complete chat program is `examples/networking/01_pygame_chat`.
