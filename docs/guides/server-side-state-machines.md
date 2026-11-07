# Using State Machines on a Server

State logic is graphics-independent, so a headless authority can advance it on
simulation ticks:

```python
from rix import StateMachine, net

match = StateMachine("waiting")

@match.state("waiting")
def waiting(_dt: float) -> None:
    pass

@match.state("playing")
def playing(_dt: float) -> None:
    pass

server = net.Server(port=7777, tick_rate=60)
server.start()
while server.state is net.ServerState.LISTENING:
    server.step()
    match.update(1 / 60)
```

For a replicated match phase, register `register_match_state()`, spawn its
prefab on `ServerReplication`, and wrap it with `ServerMatchState`. Call
`advance(server.tick_count)` after authoritative ticks. Clients use the
read-only `ClientMatchState`; receiving a revision never runs server gameplay
callbacks locally.

Menus, settings, pause, and inventory remain local `GameStates`. Only explicit
match fields—phase, round, revision, and optional tick deadline—are shared.
`examples/states/09_server_match.py` shows the headless local form, while
`examples/networking/09_authoritative_fps` shows the replicated form.
