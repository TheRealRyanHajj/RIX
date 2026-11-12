"""Authoritative native character motor with corrections and replicated visuals."""

# Usage: from the repository root, run:
#   python examples/networking/11_prediction_interpolation/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import time

import rix
from rix import net

from schema import AVATAR, registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7787)
    args = parser.parse_args()
    owner_box: list[net.ServerReplication] = []
    characters: dict[
        net.ConnectionId,
        tuple[rix.Player, net.PredictedCharacterController, net.NetworkObjectId],
    ] = {}
    accepted: set[net.ConnectionId] = set()

    def connected(_server: net.Server, connection: net.ConnectionId) -> None:
        index = len(characters)
        player = rix.Player(
            position=(index * 2.0, 0.0, 0.0),
            controls=False,
            scene=scene,
        )
        predicted = net.PredictedCharacterController(
            player.controller, role="server"
        )
        visual = owner_box[0].spawn(AVATAR)
        visual.entity.position = player.position + rix.Vec3(0, 0.9, 0)
        characters[connection] = (player, predicted, visual.id)

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        values = characters.pop(event.connection, None)
        accepted.discard(event.connection)
        if values is None:
            return
        player, _predicted, visual = values
        if player.is_alive:
            player.destroy()
        if any(item.id == visual for item in owner_box[0].objects):
            owner_box[0].despawn(visual)

    def message(server: net.Server, event: net.NetworkEvent) -> None:
        values = characters.get(event.connection)
        if values is None:
            return
        try:
            incoming = net.decode_message(event.payload)
            if incoming.name != "character_input":
                raise ValueError("unexpected application message")
            fields = incoming.fields
            command = net.CharacterInputCommand(
                fields["sequence"],  # type: ignore[arg-type]
                fields["movement"],  # type: ignore[arg-type]
                fields["heading"],  # type: ignore[arg-type]
                fields["jump"],  # type: ignore[arg-type]
                fields["sprint"],  # type: ignore[arg-type]
                fields["crouch"],  # type: ignore[arg-type]
            )
            values[1].accept(command)
            accepted.add(event.connection)
        except (KeyError, TypeError, ValueError) as error:
            server.disconnect(event.connection, f"invalid character input: {error}")

    server = net.Server(
        port=args.port,
        bind_address="0.0.0.0",
        tick_rate=60,
        on_connect=connected,
        on_disconnect=disconnected,
        on_message=message,
    )
    scene = rix.Scene("prediction authority")
    rix.Cube(
        scene=scene,
        position=(0, -0.5, 0),
        size=(40, 1, 40),
        collider=True,
    )
    server.load_scene(scene)
    owner = net.ServerReplication(server, registry())
    owner_box.append(owner)
    server.start()
    print(f"prediction authority on UDP {args.port}; Ctrl+C stops it")
    try:
        while True:
            started = time.perf_counter()
            server.step()
            for connection, (player, predicted, visual_id) in tuple(characters.items()):
                visual = next(item for item in owner.objects if item.id == visual_id)
                visual.entity.position = player.position + rix.Vec3(0, 0.9, 0)
                visual.entity.quaternion = player.quaternion
                if connection in accepted:
                    correction = predicted.make_correction(server.tick_count)
                    server.send(
                        connection,
                        net.encode_message(
                            "character_correction",
                            {
                                "ack": correction.acknowledged_sequence,
                                "tick": correction.server_tick,
                                "position": list(correction.position),
                                "rotation": list(correction.rotation),
                                "velocity": list(correction.linear_velocity),
                            },
                        ),
                    )
            accepted.clear()
            owner.flush_transforms(server.tick_count)
            time.sleep(max(0.0, 1 / 60 - (time.perf_counter() - started)))
    except KeyboardInterrupt:
        pass
    finally:
        owner.close(destroy=True)
        server.stop("operator stopped")
        server.unload_scene(clear=True)
        scene.close()


if __name__ == "__main__":
    main()
