# Pygame-only shared state

Run one host and any number of independent clients. Each process sends its
normalized Pygame cursor; only the host accepts/clamps state and broadcasts the
authoritative snapshot.

```powershell
python examples\networking\02_shared_state\main.py --host
python examples\networking\02_shared_state\main.py --address 127.0.0.1:7778
```
