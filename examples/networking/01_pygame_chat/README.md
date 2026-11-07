# Pygame chat

This is real message exchange between independent processes. It does not create
a RIX window, renderer, scene, or physics world.

From the repository root, run the server in one terminal:

```powershell
.\.venv\Scripts\python.exe examples\networking\01_pygame_chat\server.py
```

Then run one or more clients in other terminals:

```powershell
.\.venv\Scripts\python.exe examples\networking\01_pygame_chat\client.py 127.0.0.1:7777
```

The example uses direct loopback by default. For LAN use the server machine's
numeric private address. Direct IP does not solve router/firewall/NAT setup.
