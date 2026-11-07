# Client prediction and remote interpolation

The independent client predicts its local native `CharacterController`, sends
complete sequenced inputs, restores authoritative corrections, and replays only
its bounded unacknowledged suffix. Orange authority visuals use replicated
transform history through `RemoteTransformInterpolator`.

```powershell
python examples\networking\11_prediction_interpolation\server.py
python examples\networking\11_prediction_interpolation\client.py
```

WASD moves, Space jumps, Shift sprints, and Ctrl crouches. This supports the
native RIX motor only; it does not claim arbitrary Python/Jolt rollback.
