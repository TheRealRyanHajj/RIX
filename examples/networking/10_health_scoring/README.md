# Replicated health and scoring

Run the headless server and two independent Pygame clients. Space asks the
server to damage another player. The owner-checked RPC is only a request; the
server changes read-only client `NetworkVar` mirrors, resets health after an
elimination, and awards score.

```powershell
python examples\networking\10_health_scoring\server.py
python examples\networking\10_health_scoring\client.py
python examples\networking\10_health_scoring\client.py
```
