# Making a Multiplayer FPS

Begin with the working authoritative sample instead of trusting client health,
scores, positions, or hit confirmations:

```powershell
# Terminal 1
python examples\networking\09_authoritative_fps\server.py

# Terminals 2 and 3
python examples\networking\09_authoritative_fps\client.py
```

The core rule is that clients submit an action and the server decides its
result. Register a bounded owner-only request:

```python
registry.register_rpc(
    PLAYER,
    SHOOT,
    "request_shoot",
    "client_to_server",
    (("vec3", 12), ("vec3", 12)),
    validate_shot_on_server,
    rate_limit=12,
    require_owner=True,
)
```

The server handler verifies ownership, match phase, cooldown, origin/direction,
range, and the selected target before changing authoritative health or score.
Reliable delivery does not make the request truthful.

Use `PredictedCharacterController` only for RIX's supported native motor. It
sends complete sequenced move/jump/sprint/crouch input, restores corrections,
and replays a bounded suffix. Remote players use transform interpolation.
Dynamic Jolt bodies remain server-owned; this is not generic rollback.
