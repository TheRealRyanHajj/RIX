from __future__ import annotations

import time

import pytest

from rix.net import NetworkError, Player, SERVER, SendStatus, Session, SessionRole


def _host() -> tuple[Session, int]:
    for port in range(33300, 33400):
        session = Session()
        try:
            session.host(port=port, bind_address="127.0.0.1", max_players=4)
            return session, port
        except NetworkError:
            session.close()
    raise AssertionError("could not bind session test host")


def _ipv6_host() -> tuple[Session, int]:
    for port in range(33400, 33500):
        session = Session()
        try:
            session.host(
                port=port,
                bind_address="::1",
                local_address="::1",
                max_players=4,
            )
            return session, port
        except NetworkError:
            session.close()
    raise AssertionError("could not bind IPv6 session test host")


def _pump(host: Session, client: Session, predicate) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not predicate():
        host.update(1.0 / 60.0)
        client.update(1.0 / 60.0)
        time.sleep(0.001)
    assert predicate()


def test_session_routes_client_messages_and_explicit_server_broadcasts() -> None:
    host, port = _host()
    client = Session()
    received_by_host: list[tuple[Player, str]] = []
    received_by_client: list[tuple[Player, int]] = []

    @host.on("chat")
    def chat(sender: Player, *, text: str) -> None:
        received_by_host.append((sender, text))

    @client.on("score")
    def score(sender: Player, *, value: int) -> None:
        received_by_client.append((sender, value))

    try:
        client.join(f"127.0.0.1:{port}")
        _pump(
            host,
            client,
            lambda: client.role is SessionRole.CLIENT and len(host.players) == 2,
        )
        assert len([player for player in host.players if player.local]) == 1

        client.send("chat", text="hello")
        _pump(host, client, lambda: bool(received_by_host))
        sender, text = received_by_host[0]
        assert not sender.server and not sender.local
        assert text == "hello"

        statuses = host.broadcast("score", value=12)
        assert len(statuses) == 2
        _pump(host, client, lambda: bool(received_by_client))
        assert received_by_client == [(SERVER, 12)]
    finally:
        client.close()
        host.close()


def test_session_handler_removal_and_validation_are_explicit() -> None:
    session = Session()

    def handler(*_args: object, **_fields: object) -> None:
        pass

    session.on("notice")(handler)
    with pytest.raises(ValueError, match="already registered"):
        session.on("notice")(handler)
    assert session.off("notice", handler)
    assert not session.off("notice", handler)
    with pytest.raises(ValueError, match="reserved"):
        session.send("connect")
    with pytest.raises(NetworkError, match="not connected"):
        session.send("notice", value=True)
    with pytest.raises(ValueError, match="non-empty"):
        session.on("")
    assert session.update(0.0) == 0
    with pytest.raises(ValueError, match="non-negative"):
        session.update(-0.1)


def test_session_routes_over_numeric_ipv6_and_bracketed_join_address() -> None:
    host, port = _ipv6_host()
    client = Session()
    received: list[str] = []

    @host.on("ipv6")
    def ipv6_message(_sender: Player, *, text: str) -> None:
        received.append(text)

    try:
        client.join(f"[::1]:{port}")
        _pump(host, client, lambda: len(host.players) == 2)
        assert client.send("ipv6", text="loopback") is SendStatus.QUEUED
        _pump(host, client, lambda: received == ["loopback"])
    finally:
        client.close()
        host.close()
