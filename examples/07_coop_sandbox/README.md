# Cooperative replication sandbox

This finite headless sample exercises the real public Easy3D client/server,
prefab, `NetworkVar`, transform, ownership and RPC APIs over GameNetworkingSockets
loopback. It supports 2–8 clients and exits after all clients observe synchronized
players and the authoritative crate destruction.

From the repository root in the installed Python 3.11 environment:

```powershell
python examples/07_coop_sandbox/main.py --clients 2
python examples/07_coop_sandbox/main.py --clients 8
```

This is a deterministic local integration scenario, not a rendered game,
prediction demo, LAN discovery test or 32-player performance claim.
