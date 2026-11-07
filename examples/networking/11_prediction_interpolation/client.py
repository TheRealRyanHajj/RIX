"""Predict local native movement, reconcile, and interpolate remote visuals."""

from __future__ import annotations

import argparse

import pygame
import rix
from rix import net

from schema import registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7787)
    args = parser.parse_args()
    pygame.init()
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 30)
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    world = rix.World(screen)
    world.set_overlay(overlay)
    rix.Plane(world, y=-0.5, size=40, color="#334155")
    local = rix.Player(world, position=(0, 0, 0), controls=False)
    predicted = net.PredictedCharacterController(local.controller, role="client")
    client = net.Client()
    mirror = net.ClientReplication(client, world.scene, registry())
    interpolation = net.RemoteTransformInterpolator(mirror, delay_ticks=2)
    client.connect(args.address, args.port)
    authority_tick = 0
    jump_was_down = False
    try:
        while world.running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                world.handle_event(event)
            keys = pygame.key.get_pressed()
            jump_down = bool(keys[pygame.K_SPACE])
            movement = (
                float(keys[pygame.K_d] - keys[pygame.K_a]),
                0.0,
                float(keys[pygame.K_s] - keys[pygame.K_w]),
            )
            if client.state is net.ClientState.CONNECTED:
                command = predicted.submit(
                    movement,
                    jump=jump_down and not jump_was_down,
                    sprint=bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]),
                    crouch=bool(keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]),
                )
                client.send(
                    net.encode_message(
                        "character_input",
                        {
                            "sequence": command.sequence,
                            "movement": list(command.movement),
                            "heading": command.heading_degrees,
                            "jump": command.jump,
                            "sprint": command.sprint,
                            "crouch": command.crouch,
                        },
                    )
                )
            jump_was_down = jump_down
            for event in mirror.poll():
                if event.type is not net.EventType.MESSAGE:
                    continue
                message = net.decode_message(event.payload)
                if message.name != "character_correction":
                    continue
                correction = net.CharacterCorrection(
                    message.fields["ack"],  # type: ignore[arg-type]
                    message.fields["tick"],  # type: ignore[arg-type]
                    message.fields["position"],  # type: ignore[arg-type]
                    message.fields["rotation"],  # type: ignore[arg-type]
                    message.fields["velocity"],  # type: ignore[arg-type]
                )
                predicted.reconcile(correction, fixed_delta_seconds=1 / 60)
                authority_tick = max(authority_tick, correction.server_tick)
            for item in mirror.objects:
                samples = mirror.transform_snapshots(item.id)
                if samples:
                    authority_tick = max(authority_tick, samples[-1].tick)
            if mirror.is_synchronized:
                interpolation.update(authority_tick)
            world.camera.position = local.position + rix.Vec3(0, 3.0, 6.0)
            world.camera.look_at(local.position + rix.Vec3(0, 0.8, 0))
            stats = predicted.correction_stats
            overlay.fill((0, 0, 0, 0))
            overlay.blit(
                font.render(
                    f"pending {len(predicted.pending_inputs)}  corrections {stats.corrections}  "
                    f"last error {stats.last_position_error:.3f}",
                    True,
                    "white",
                ),
                (20, 20),
            )
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
