# Isolated listen host

Run from the repository root:

```powershell
python examples/05_listen_host/main.py --port 7777
```

The example creates one authoritative `Server` role and one local `Client`
role connected through the real loopback transport. The authority alone owns
the scene and executes `fixed_update`; the local client sends input-like bytes
and receives an authority reply. Tagged output makes the two role-local
connection-ID spaces explicit even when both happen to contain numeric ID 1.

This Phase 3.6 example is headless. Attaching the local client role to a
rendered `Game`, LAN discovery, player identity and replication remain later
milestones.
