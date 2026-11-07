# Network latency/loss simulator

This finite example compares RIX's seeded LAN, regional, and adverse profiles:

```powershell
.\.venv\Scripts\python.exe examples\networking\12_network_conditions\main.py
```

Use `--profile regional`, `--messages 500`, or `--seed 9` to change the run.
It advances a native in-memory packet simulator using virtual time, so the same
seed produces the same ordering and loss without waiting in real time.

This is deliberately a deterministic test/demo transport. It is not a fake
multiplayer client and it does not claim to model GameNetworkingSockets'
reliable retransmission. Use `net.impair_backend(profile)` in integration tests
when exercising the real native socket backend under injected conditions.
