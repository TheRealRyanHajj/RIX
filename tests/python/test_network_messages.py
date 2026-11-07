from __future__ import annotations

import math
import socket
import time

import pytest

from rix import net


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_message_codec_round_trips_only_safe_basic_values() -> None:
    frame = net.encode_message(
        "state",
        {
            "ready": True,
            "score": 7,
            "position": [1.0, 2.0, 3.0],
            "label": "player",
            "blob": b"\x00\xff",
            "optional": None,
        },
    )
    message = net.decode_message(frame)
    assert message.name == "state"
    assert message.fields["position"] == [1.0, 2.0, 3.0]
    assert message.fields["blob"] == b"\x00\xff"


@pytest.mark.parametrize("value", [object(), math.inf, math.nan, 2**64])
def test_message_codec_rejects_unsafe_or_unbounded_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        net.encode_message("unsafe", {"value": value})


def test_session_message_schemas_validate_outgoing_fields() -> None:
    session = net.Session()
    schema = session.register_message("score", value=int, label=(str, type(None)))
    schema.validate({"value": 4, "label": None})
    with pytest.raises(TypeError, match="value"):
        schema.validate({"value": True, "label": "player"})
    with pytest.raises(ValueError, match="missing"):
        schema.validate({"value": 4})
    with pytest.raises(ValueError, match="undeclared"):
        schema.validate({"value": 4, "label": "p", "extra": 1})
    with pytest.raises(ValueError, match="already registered"):
        session.register_message("score", value=int)
    assert session.unregister_message("score")
    assert not session.unregister_message("score")


def test_invalid_registered_message_disconnects_the_sender() -> None:
    port = _free_port()
    host = net.Session()
    host.register_message("score", value=int)
    client = net.Client(timeout=1, peer_timeout=2)
    host.host(port=port, bind_address="127.0.0.1")
    try:
        client.connect("127.0.0.1", port)
        deadline = time.monotonic() + 2.0
        while len(host.players) < 2 and time.monotonic() < deadline:
            host.update()
            client.poll()
            time.sleep(0.001)
        assert len(host.players) == 2
        assert client.send(net.encode_message("score", {"value": "bad"})) is net.SendStatus.QUEUED
        with pytest.raises(net.NetworkError, match="invalid application message"):
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                host.update()
                client.poll()
                time.sleep(0.001)
        deadline = time.monotonic() + 2.0
        while client.connection is not None and time.monotonic() < deadline:
            host.update()
            client.poll()
            time.sleep(0.001)
        assert client.connection is None
    finally:
        if client.connection is not None:
            client.disconnect("cleanup")
            client.poll()
        host.close()


def test_listen_session_has_real_local_client_and_dispatches_messages() -> None:
    session = net.Session()
    received: list[tuple[net.Player, str]] = []
    connected: list[net.Player] = []

    @session.on("connect")
    def connected_player(player: net.Player) -> None:
        connected.append(player)

    @session.on("chat")
    def chat(player: net.Player, text: str) -> None:
        received.append((player, text))

    session.host(port=_free_port(), bind_address="127.0.0.1")
    try:
        assert len(session.players) == 1
        assert session.players[0].local
        assert connected == [session.players[0]]
        assert session.send("chat", text="hello") is net.SendStatus.QUEUED
        deadline = time.monotonic() + 2.0
        while not received and time.monotonic() < deadline:
            session.update(1.0 / 60.0)
            time.sleep(0.001)
        assert received == [(session.players[0], "hello")]
    finally:
        session.close()


def test_host_startup_callback_failure_closes_transport_transactionally() -> None:
    port = _free_port()
    session = net.Session()

    @session.on("connect")
    def fail_startup(_player: net.Player) -> None:
        raise RuntimeError("application startup failed")

    with pytest.raises(RuntimeError, match="application startup failed"):
        session.host(port=port, bind_address="127.0.0.1")
    assert session.role is net.SessionRole.CLOSED
    assert not session.is_open
    assert session.players == ()

    # Removing the failing callback and reusing the exact port proves host()
    # released the native listener instead of only resetting Python fields.
    assert session.off("connect", fail_startup)
    session.host(port=port, bind_address="127.0.0.1")
    try:
        assert session.role is net.SessionRole.HOST
        assert session.is_open
    finally:
        session.close()
