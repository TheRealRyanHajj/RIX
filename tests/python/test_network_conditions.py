from __future__ import annotations

import time

import pytest

from rix.net import (
    ADVERSE_NETWORK_CONDITION,
    LAN_NETWORK_CONDITION,
    REPRESENTATIVE_NETWORK_CONDITIONS,
    Client,
    ClientState,
    Delivery,
    EventType,
    NetworkCondition,
    NetworkError,
    SendStatus,
    Server,
    impair_backend,
)


def _server() -> Server:
    for port in range(32800, 32900):
        server = Server(port=port, bind_address="127.0.0.1", peer_timeout=5.0)
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind network-condition test server")


def test_representative_profiles_are_seeded_and_bounded() -> None:
    assert [profile.name for profile in REPRESENTATIVE_NETWORK_CONDITIONS] == [
        "lan",
        "regional",
        "adverse",
    ]

    observed: dict[str, tuple[int, int]] = {}
    for profile in REPRESENTATIVE_NETWORK_CONDITIONS:
        link = profile.create_simulated_link(seed=53)
        link.first.poll()
        link.second.poll()
        for sequence in range(500):
            assert link.first.send(
                sequence.to_bytes(2, "little"), delivery=Delivery.UNRELIABLE
            ) is SendStatus.QUEUED
        link.advance(profile.one_way_latency_seconds + profile.jitter_seconds + 0.001)
        delivered = [
            event for event in link.second.poll(1000) if event.type is EventType.MESSAGE
        ]
        lost = link.first.stats.messages_lost
        assert len(delivered) + lost == 500
        assert link.in_flight_count == 0
        observed[profile.name] = (len(delivered), lost)

        repeat = profile.create_simulated_link(seed=53)
        repeat.first.poll()
        repeat.second.poll()
        for sequence in range(500):
            repeat.first.send(
                sequence.to_bytes(2, "little"), delivery=Delivery.UNRELIABLE
            )
        repeat.advance(profile.one_way_latency_seconds + profile.jitter_seconds + 0.001)
        repeat_delivered = [
            event.payload
            for event in repeat.second.poll(1000)
            if event.type is EventType.MESSAGE
        ]
        assert repeat_delivered == [event.payload for event in delivered]
        assert repeat.first.stats.messages_lost == lost

    assert observed["lan"] == (500, 0)
    assert 0 < observed["regional"][1] < 50
    assert 0 < observed["adverse"][1] < 100


def test_total_loss_is_explicit_and_delivers_no_application_messages() -> None:
    outage = NetworkCondition("outage", 0.1, 0.03, 1.0)
    link = outage.create_simulated_link(seed=9)
    link.first.poll()
    link.second.poll()
    for _ in range(64):
        assert link.first.send(b"input") is SendStatus.QUEUED
    link.advance(0.2)
    assert link.second.poll() == ()
    assert link.first.stats.messages_lost == 64


def test_seeded_jitter_reorders_unreliable_messages_deterministically() -> None:
    def trace() -> tuple[int, ...]:
        link = NetworkCondition("reorder", 0.03, 0.02, 0.0).create_simulated_link(
            seed=99
        )
        link.first.poll()
        link.second.poll()
        for sequence in range(20):
            assert link.first.send(
                bytes([sequence]), delivery=Delivery.UNRELIABLE
            ) is SendStatus.QUEUED
        link.advance(0.1)
        return tuple(
            event.payload[0]
            for event in link.second.poll()
            if event.type is EventType.MESSAGE
        )

    first = trace()
    assert first == trace()
    assert sorted(first) == list(range(20))
    assert first != tuple(range(20))


def test_real_backend_reliably_recovers_under_adverse_profile() -> None:
    server = _server()
    client = Client(timeout=8.0, peer_timeout=5.0)
    received: list[bytes] = []
    try:
        with impair_backend(ADVERSE_NETWORK_CONDITION):
            with pytest.raises(NetworkError, match="process-global"):
                with impair_backend(LAN_NETWORK_CONDITION):
                    pass

            client.connect("127.0.0.1", server.port)
            connect_deadline = time.monotonic() + 8.0
            while time.monotonic() < connect_deadline:
                server.poll()
                client.poll()
                if client.state is ClientState.CONNECTED and server.connections:
                    break
                time.sleep(0.001)
            assert client.state is ClientState.CONNECTED
            assert len(server.connections) == 1

            payloads = [index.to_bytes(4, "little") for index in range(32)]
            for payload in payloads:
                assert client.send(payload, delivery=Delivery.RELIABLE) is SendStatus.QUEUED

            receive_deadline = time.monotonic() + 8.0
            while time.monotonic() < receive_deadline and len(received) < len(payloads):
                for event in server.poll():
                    if event.type is EventType.MESSAGE:
                        received.append(event.payload)
                client.poll()
                time.sleep(0.001)
            assert received == payloads
    finally:
        if client.connection is not None:
            client.disconnect("condition test complete")
            client.poll()
        server.stop()


@pytest.mark.parametrize(
    "arguments",
    [
        ("", 0.0, 0.0, 0.0),
        ("bad", -0.1, 0.0, 0.0),
        ("bad", 0.0, 2.1, 0.0),
        ("bad", 0.0, 0.0, 1.1),
    ],
)
def test_network_condition_validation(arguments: tuple[object, ...]) -> None:
    with pytest.raises((TypeError, ValueError)):
        NetworkCondition(*arguments)  # type: ignore[arg-type]
