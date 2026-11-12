"""Independent Pygame+RIX client for authoritative FPS rules."""

# Usage: from the repository root, run:
#   python examples/networking/09_authoritative_fps/client.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import math

import pygame
import rix
from rix import net

from schema import HEALTH, MATCH, MOVE, SCORE, SHOOT, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7785)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 34)
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    world = rix.World(screen)
    world.set_overlay(overlay)
    rix.Plane(world, y=0, size=35, color="#334155")
    client = net.Client()
    mirror = net.ClientReplication(client, world.scene, registry())
    interpolation = net.RemoteTransformInterpolator(mirror, delay_ticks=2)
    client.connect(args.address, args.port)
    authority_tick = 0
    yaw = 180.0
    shoot_was_down = False
    try:
        while world.running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                world.handle_event(event)
            mirror.poll()
            local = next(
                (
                    item
                    for item in mirror.objects
                    if getattr(item.entity, "network_local_id", None) == item.id.value
                ),
                None,
            )
            keys = pygame.key.get_pressed()
            yaw += float(keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * 100 * dt
            radians = math.radians(yaw)
            forward = rix.Vec3(math.sin(radians), 0, -math.cos(radians))
            right = rix.Vec3(math.cos(radians), 0, math.sin(radians))
            movement = (
                forward * float(keys[pygame.K_w] - keys[pygame.K_s])
                + right * float(keys[pygame.K_d] - keys[pygame.K_a])
            )
            if movement.length > 1:
                movement = movement.normalized()
            if local is not None and movement.length:
                mirror.call_server(local.id, MOVE, movement.x, movement.z)
            shooting = bool(keys[pygame.K_SPACE])
            if local is not None and shooting and not shoot_was_down:
                mirror.call_server(local.id, SHOOT, forward.x, forward.y, forward.z)
            shoot_was_down = shooting
            for item in mirror.objects:
                samples = mirror.transform_snapshots(item.id)
                if samples:
                    authority_tick = max(authority_tick, samples[-1].tick)
            if mirror.is_synchronized:
                interpolation.update(authority_tick)
            health = score = 0
            phase = "WAITING"
            if local is not None:
                health = int(mirror.variable(local.id, HEALTH).value)
                score = int(mirror.variable(local.id, SCORE).value)
                world.camera.position = local.entity.position + rix.Vec3(0, 1.0, 0)
                world.camera.rotation = (0, yaw, 0)
            match_object = next(
                (item for item in mirror.objects if item.prefab_id.value == MATCH),
                None,
            )
            if match_object is not None:
                phase = net.ClientMatchState(mirror, match_object.id).phase.name
            overlay.fill((0, 0, 0, 0))
            overlay.blit(
                font.render(f"{phase}  Health {health}  Score {score}", True, "white"),
                (20, 20),
            )
            pygame.draw.line(overlay, "white", (630, 360), (650, 360), 2)
            pygame.draw.line(overlay, "white", (640, 350), (640, 370), 2)
            world.overlay.update(overlay)
            world.update(dt)
            world.render()
    finally:
        mirror.clear()
        if client.connection is not None:
            client.disconnect("client closed")
            client.poll()
        world.close()
        pygame.quit()


if __name__ == "__main__":
    main()
