from __future__ import annotations

import pytest

from rix import Cube, Player, Scene, Vec3
from rix.net import (
    CharacterCorrection,
    CharacterInputCommand,
    NetworkError,
    PredictedCharacterController,
    PredictionRole,
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
        move_speed=3.0,
        scene=scene,
    )
    _step(scene, 5)
    return scene, player


def _step(scene: Scene, count: int = 1) -> None:
    for _ in range(count):
        scene._native.step_physics(1.0 / 60.0)


def test_character_input_command_captures_all_motor_intent() -> None:
    command = CharacterInputCommand(
        7,
        Vec3(1.0, 0.0, -1.0),
        45,
        True,
        True,
        False,
    )
    assert command.sequence == 7
    assert command.movement == (1.0, 0.0, -1.0)
    assert command.heading_degrees == 45.0
    assert command.jump is True
    assert command.sprint is True
    assert command.crouch is False

    with pytest.raises((AttributeError, TypeError)):
        command.sequence = 8  # type: ignore[misc]
    with pytest.raises(ValueError, match="sequence"):
        CharacterInputCommand(0, (0.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="finite"):
        CharacterInputCommand(1, (0.0, 0.0, 0.0), float("nan"))
    with pytest.raises(TypeError, match="sprint"):
        CharacterInputCommand(1, (0.0, 0.0, 0.0), sprint=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="crouch"):
        CharacterInputCommand(1, (0.0, 0.0, 0.0), crouch=1)  # type: ignore[arg-type]


def test_client_submission_is_immediate_bounded_and_acknowledged() -> None:
    scene, player = _character()
    predicted = PredictedCharacterController(
        player.controller, role="client", max_pending_inputs=2
    )
    assert predicted.role is PredictionRole.CLIENT
    assert predicted.last_input_sequence == 0

    first = predicted.submit(
        (0.0, 0.0, 1.0), heading_degrees=30.0, sprint=True
    )
    second = predicted.submit(
        (1.0, 0.0, 0.0), heading_degrees=90.0, jump=True
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert predicted.last_input_sequence == 2
    assert predicted.pending_inputs == (first, second)
    _step(scene, 10)
    assert player.position.y > 0.0

    with pytest.raises(NetworkError, match="queue is full"):
        predicted.submit((0.0, 0.0, 0.0))
    assert predicted.acknowledge(1) == 1
    assert predicted.pending_inputs == (second,)
    assert predicted.acknowledge(2) == 1
    assert predicted.pending_inputs == ()


def test_server_rejects_duplicate_and_stale_commands_without_mutation() -> None:
    _scene, player = _character()
    predicted = PredictedCharacterController(player.controller, role="server")
    predicted.accept(CharacterInputCommand(4, (0.0, 0.0, 1.0)))
    assert predicted.last_input_sequence == 4

    for sequence in (4, 3):
        with pytest.raises(ValueError, match="strictly increasing"):
            predicted.accept(CharacterInputCommand(sequence, (1.0, 0.0, 0.0)))
        assert predicted.last_input_sequence == 4

    with pytest.raises(NetworkError, match="client role"):
        predicted.submit((0.0, 0.0, 0.0))


def test_client_and_server_apply_identical_full_motor_inputs() -> None:
    client_scene, client_player = _character()
    server_scene, server_player = _character()
    client = PredictedCharacterController(client_player.controller, role="client")
    server = PredictedCharacterController(server_player.controller, role="server")

    inputs = (
        ((0.0, 0.0, 1.0), 0.0, False, True, False, 20),
        ((1.0, 0.0, 0.0), 90.0, False, False, True, 10),
        ((0.0, 0.0, 0.0), 90.0, True, False, False, 10),
    )
    for movement, heading, jump, sprint, crouch, steps in inputs:
        command = client.submit(
            movement,
            heading_degrees=heading,
            jump=jump,
            sprint=sprint,
            crouch=crouch,
        )
        server.accept(command)
        _step(client_scene, steps)
        _step(server_scene, steps)

    assert client.last_input_sequence == server.last_input_sequence == 3
    assert client_player.position.almost_equal(server_player.position, 1.0e-5)
    assert client_player.controller.linear_velocity.almost_equal(
        server_player.controller.linear_velocity, 1.0e-5
    )
    assert client_player.controller.crouched == server_player.controller.crouched
    assert client_player.quaternion.almost_equal(server_player.quaternion, 1.0e-5)


def test_authoritative_correction_replays_pending_full_input() -> None:
    client_scene, client_player = _character()
    server_scene, server_player = _character()
    client = PredictedCharacterController(client_player.controller, role="client")
    server = PredictedCharacterController(server_player.controller, role="server")

    first = client.submit((0.0, 0.0, 1.0), heading_degrees=15.0)
    server.accept(first)
    _step(client_scene)
    _step(server_scene)
    correction_one = server.make_correction(1)

    second = client.submit(
        (1.0, 0.0, 0.0),
        heading_degrees=60.0,
        sprint=True,
        crouch=False,
    )
    _step(client_scene)
    server.accept(second)
    _step(server_scene)

    result = client.reconcile(correction_one, fixed_delta_seconds=1.0 / 60.0)
    assert result.acknowledged_sequence == 1
    assert result.replayed_inputs == 1
    assert client.pending_inputs == (second,)
    assert client_player.position.almost_equal(server_player.position, 1.0e-5)
    assert client_player.controller.linear_velocity.almost_equal(
        server_player.controller.linear_velocity, 1.0e-5
    )


def test_character_prediction_state_resets_when_native_slot_is_reused() -> None:
    scene, first_player = _character()
    first_player.controller.set_sequenced_input(9, (0.0, 0.0, 1.0))
    assert first_player.controller.last_input_sequence == 9
    first_player.destroy()

    second_player = Player(
        position=(2.0, 0.0, 0.0),
        controller="first_person",
        controls=False,
        scene=scene,
    )
    assert second_player.controller.last_input_sequence == 0
    second_player.controller.set_sequenced_input(1, (0.0, 0.0, 1.0))
    assert second_player.controller.last_input_sequence == 1


def test_correction_validation_and_role_boundaries() -> None:
    _scene, player = _character()
    client = PredictedCharacterController(player.controller, role="client")
    server = PredictedCharacterController(player.controller, role="server")
    initial = CharacterCorrection(
        0,
        0,
        (1.0, 2.0, 3.0),
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
    )
    result = client.reconcile(initial, fixed_delta_seconds=1.0 / 60.0)
    assert result.replayed_inputs == 0
    assert player.position.almost_equal(Vec3(1.0, 2.0, 3.0), 1.0e-5)
    with pytest.raises(NetworkError, match="server role"):
        client.make_correction(1)
    with pytest.raises(NetworkError, match="client role"):
        server.reconcile(initial, fixed_delta_seconds=1.0 / 60.0)
