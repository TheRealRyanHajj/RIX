from __future__ import annotations

import pytest

from easy3d import (
    CharacterInputCommand,
    Cube,
    NetworkError,
    Player,
    PredictedCharacterController,
    PredictionRole,
    Scene,
    Vec3,
)


def _character() -> tuple[Scene, Player]:
    scene = Scene("prediction")
    Cube(
        position=(0.0, -0.5, 0.0),
        size=(30.0, 1.0, 30.0),
        collider=True,
        scene=scene,
    )
    player = Player(
        position=(0.0, 0.0, 0.0),
        controller="first_person",
        speed=3.0,
        scene=scene,
    )
    for _ in range(5):
        scene._native.step_physics(1.0 / 60.0)
    return scene, player


def _step(scene: Scene, count: int = 1) -> None:
    for _ in range(count):
        scene._native.step_physics(1.0 / 60.0)


def test_character_input_command_is_typed_normalized_and_immutable() -> None:
    command = CharacterInputCommand(7, Vec3(1.0, 0.0, -1.0), 45, True)
    assert command.sequence == 7
    assert command.movement == (1.0, 0.0, -1.0)
    assert command.heading_degrees == 45.0
    assert command.jump is True

    with pytest.raises((AttributeError, TypeError)):
        command.sequence = 8  # type: ignore[misc]
    with pytest.raises(ValueError, match="sequence"):
        CharacterInputCommand(0, (0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="finite"):
        CharacterInputCommand(1, (0.0, 0.0, 0.0), float("nan"))
    with pytest.raises(TypeError, match="jump"):
        CharacterInputCommand(1, (0.0, 0.0, 0.0), jump=1)  # type: ignore[arg-type]


def test_client_submission_is_immediate_bounded_and_acknowledged() -> None:
    scene, player = _character()
    predicted = PredictedCharacterController(
        player.controller, role="client", max_pending_inputs=2
    )
    assert predicted.role is PredictionRole.CLIENT
    assert predicted.last_input_sequence == 0

    first = predicted.submit((0.0, 0.0, 1.0), heading_degrees=30.0)
    second = predicted.submit((1.0, 0.0, 0.0), heading_degrees=90.0, jump=True)
    assert (first.sequence, second.sequence) == (1, 2)
    assert predicted.last_input_sequence == 2
    assert predicted.pending_inputs == (first, second)
    _step(scene, 10)
    assert player.position.y > 0.0

    with pytest.raises(NetworkError, match="queue is full"):
        predicted.submit((0.0, 0.0, 0.0))
    assert predicted.last_input_sequence == 2
    assert predicted.acknowledge(1) == 1
    assert predicted.pending_inputs == (second,)
    assert predicted.last_acknowledged_sequence == 1
    assert predicted.acknowledge(2) == 1
    assert predicted.pending_inputs == ()
    with pytest.raises(ValueError, match="backwards"):
        predicted.acknowledge(1)
    with pytest.raises(ValueError, match="not submitted"):
        predicted.acknowledge(3)


def test_server_rejects_duplicate_and_stale_commands_without_mutation() -> None:
    _scene, player = _character()
    predicted = PredictedCharacterController(player.controller, role="server")
    command = CharacterInputCommand(4, (0.0, 0.0, 1.0))
    predicted.accept(command)
    assert predicted.last_input_sequence == 4
    assert predicted.pending_inputs == ()

    for sequence in (4, 3):
        with pytest.raises(ValueError, match="strictly increasing"):
            predicted.accept(CharacterInputCommand(sequence, (1.0, 0.0, 0.0)))
        assert predicted.last_input_sequence == 4

    with pytest.raises(NetworkError, match="client role"):
        predicted.submit((0.0, 0.0, 0.0))
    with pytest.raises(NetworkError, match="client role"):
        predicted.acknowledge(4)


def test_client_and_server_apply_identical_native_motor_inputs() -> None:
    client_scene, client_player = _character()
    server_scene, server_player = _character()
    client = PredictedCharacterController(client_player.controller, role="client")
    server = PredictedCharacterController(server_player.controller, role="server")

    inputs = (
        ((0.0, 0.0, 1.0), 0.0, False, 20),
        ((1.0, 0.0, 0.0), 90.0, False, 20),
        ((0.0, 0.0, 0.0), 90.0, True, 10),
    )
    for movement, heading, jump, steps in inputs:
        command = client.submit(
            movement, heading_degrees=heading, jump=jump
        )
        server.accept(command)
        _step(client_scene, steps)
        _step(server_scene, steps)

    assert client.last_input_sequence == server.last_input_sequence == 3
    assert client_player.position.almost_equal(server_player.position, 1.0e-5)
    assert client_player.controller.linear_velocity.almost_equal(
        server_player.controller.linear_velocity, 1.0e-5
    )
    assert client_player.quaternion.almost_equal(server_player.quaternion, 1.0e-5)


def test_sequence_exhaustion_and_role_validation_are_explicit() -> None:
    _scene, player = _character()
    client = PredictedCharacterController(player.controller, role="client")
    client._next_sequence = (1 << 64) - 1
    with pytest.raises(NetworkError, match="exhausted"):
        client.submit((0.0, 0.0, 0.0))
    assert client.pending_inputs == ()
    assert client.last_input_sequence == 0

    with pytest.raises(ValueError, match="role"):
        PredictedCharacterController(player.controller, role="peer")
    with pytest.raises(ValueError, match="positive"):
        PredictedCharacterController(
            player.controller, role="client", max_pending_inputs=0
        )


def test_direct_character_sequence_surface_preserves_offline_input() -> None:
    _scene, player = _character()
    controller = player.controller
    controller.set_input((1.0, 0.0, 0.0))
    assert controller.last_input_sequence == 0
    controller.set_sequenced_input(2, (0.0, 0.0, 1.0))
    assert controller.last_input_sequence == 2
    with pytest.raises(ValueError, match="strictly increasing"):
        controller.set_sequenced_input(2, (1.0, 0.0, 0.0))
    assert controller.last_input_sequence == 2
