# RIX multiplayer examples

These 13 examples use the public `rix.net` API. Run commands from the repository
root with the interpreter that installed the editable checkout. Examples with
separate `server.py` and `client.py` files require independent terminals.

1. `00_tic_tac_toe` — authoritative two-player messages in independent Pygame
   clients.
2. `01_pygame_chat` — headless chat server and Pygame-only chat client.
3. `02_shared_state` — Pygame-only clients sharing authoritative cursor state.
4. `03_listen_server` — finite listen server with an isolated local client.
5. `04_dedicated_server` — independent headless server and Pygame client.
6. `05_lan_discovery` — UDP LAN announcement, discovery, then Session join.
7. `06_direct_ip` — numeric-address native client/server connection.
8. `07_synchronized_cubes` — registered-prefab transform replication.
9. `08_cooperative_3d` — owner-checked movement and a shared objective.
10. `09_authoritative_fps` — server-owned match, movement, shooting, health,
    and score.
11. `10_health_scoring` — focused replicated health and scoring rules.
12. `11_prediction_interpolation` — native character prediction,
    reconciliation, and remote transform interpolation.
13. `12_network_conditions` — finite seeded latency/jitter/loss simulation.

Start a two-process example like this:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe examples\networking\04_dedicated_server\server.py

# Terminal 2
.\.venv\Scripts\python.exe examples\networking\04_dedicated_server\client.py
```

The examples do not imply hosted matchmaking, arbitrary NAT traversal, a
managed relay service, or generic rollback. The latency/loss simulator is
explicitly synthetic; all other multiplayer examples use real independent
native connections.

The optional self-hosted room-code directory is a reference service rather
than a fourteenth game example:

```powershell
python examples\networking\signaling.py serve
python examples\networking\signaling.py register PLAY-234 127.0.0.1:7777
python examples\networking\signaling.py resolve PLAY-234
```

The registration process must remain connected. The directory removes its room
automatically on disconnect. Resolution only returns a numeric direct endpoint;
it does not relay packets or make an unreachable server reachable through NAT.
