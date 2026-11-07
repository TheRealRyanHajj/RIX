# Two-player cooperative 3D game

Run the headless server and two independent clients. Each client owns only its
input RPC; the server validates ownership and applies movement, then replicates
all player transforms and the shared orange objective.

```powershell
python examples\networking\08_cooperative_3d\server.py
python examples\networking\08_cooperative_3d\client.py
python examples\networking\08_cooperative_3d\client.py
```

Use WASD. This example intentionally sends input direction rather than trusting
a client-provided final position.
