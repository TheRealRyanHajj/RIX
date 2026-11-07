# Server-authoritative FPS rules

Run one headless server and two independent clients. WASD sends owner-checked
movement input, arrow keys rotate the local view, and Space requests a shot.
The server—not the client—selects a target from the authoritative positions,
applies health, awards score, respawns, and owns the replicated match phase.

```powershell
python examples\networking\09_authoritative_fps\server.py
python examples\networking\09_authoritative_fps\client.py
python examples\networking\09_authoritative_fps\client.py
```

This is a compact networking/security example, not a finished shooter or an
anti-cheat claim.
