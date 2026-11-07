# Separate dedicated server and client

The server is an independent headless authority and is not a player. The client
is an independent Pygame process. Press Space in the client to send a safe
`ping` frame and display the server's validated `pong`.

```powershell
python examples\networking\04_dedicated_server\server.py
python examples\networking\04_dedicated_server\client.py
```

No window, renderer, Pygame import, or GPU is initialized by `server.py`.
