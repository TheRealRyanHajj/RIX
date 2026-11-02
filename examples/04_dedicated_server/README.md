# Headless dedicated server

From the repository root in the supported Python environment:

```powershell
python examples/04_dedicated_server/main.py --port 7777
```

The process binds a numeric direct-IP address, runs Python `fixed_update`
logic and native scene physics at 60 Hz, and creates no SDL window or bgfx
device. Press Ctrl+C to stop. For a bounded smoke run:

```powershell
python examples/04_dedicated_server/main.py --bind 127.0.0.1 --port 7777 --seconds 2
```

Phase 3.5 intentionally provides transport and authoritative simulation only.
It does not yet spawn players, replicate entities, discover LAN servers or run
a local listen-server client.
