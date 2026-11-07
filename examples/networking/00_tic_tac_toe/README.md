# Two-player Tic-Tac-Toe

This is message-only multiplayer: two independent Pygame processes, no RIX
renderer or physics. The host is the authority and validates turn order and
empty cells.

```powershell
python examples\networking\00_tic_tac_toe\main.py --host
python examples\networking\00_tic_tac_toe\main.py --address 127.0.0.1:7777
```

The host participates through its separate local client identity. Messages use
registered schemas and no process shares Python game objects with the other.
