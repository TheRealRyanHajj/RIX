# Joining a Game

Joining creates only a client. It never starts an authority in the background:

```python
import pygame
from rix import net

pygame.init()
screen = pygame.display.set_mode((800, 600))
clock = pygame.time.Clock()
session = net.Session()
session.join("127.0.0.1:7777")

running = True
try:
    while running and session.is_open:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        session.update(dt)
        screen.fill("black")
        pygame.display.flip()
finally:
    session.close()
    pygame.quit()
```

Numeric IPv6 uses brackets when a port is present, for example
`session.join("[::1]:7777")`. Direct IP requires a genuinely reachable server;
RIX does not automatically open a firewall or router port.

For the optional self-hosted room directory, resolve a code with
`SignalingClient`, then pass `event.endpoint.connection_string` to `join()`.
That lookup is signaling only—the game still uses a direct connection.
