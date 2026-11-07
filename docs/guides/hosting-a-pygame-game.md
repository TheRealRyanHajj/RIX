# Hosting a Pygame Game

Pygame keeps its normal event and drawing loop. Poll one nonblocking `Session`
beside it:

```python
import pygame
from rix import net

pygame.init()
screen = pygame.display.set_mode((800, 600))
clock = pygame.time.Clock()
session = net.Session()
session.host(port=7777, bind_address="0.0.0.0")

running = True
try:
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        session.update(dt)
        screen.fill("navy")
        pygame.display.flip()
finally:
    session.close()
    pygame.quit()
```

`host()` creates one authority plus a separate real local-client identity. It
does not duplicate the authoritative simulation. When the same application has
a RIX `World`, call `world.attach_session(session)` once and let
`world.update(dt)` poll it. Do not also call `session.update(dt)`.

For LAN guests, bind to `0.0.0.0` and connect to the host's numeric private
address. Optional LAN discovery can advertise the address; it is a hint, not
authentication or NAT traversal.
