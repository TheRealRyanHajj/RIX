# RIX 3D synchronized cubes

These are independent processes. The headless server owns three registered
cube entities and sends transform snapshots; the Pygame+RIX client constructs
only the locally registered prefab and renders with a two-tick interpolation
delay.

```powershell
python examples\networking\07_synchronized_cubes\server.py
python examples\networking\07_synchronized_cubes\client.py
```
