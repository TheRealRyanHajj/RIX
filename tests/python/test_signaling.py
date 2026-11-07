from __future__ import annotations

import time

import pytest

from rix import net


def _server(*, max_rooms: int = 8) -> net.SignalingServer:
    for port in range(33500, 33600):
        server = net.SignalingServer(
            port=port,
            bind_address="127.0.0.1",
            max_rooms=max_rooms,
        )
        try:
            server.start()
            return server
        except net.NetworkError:
            server.stop()
    raise AssertionError("could not bind signaling test server")


def _pump(
    server: net.SignalingServer,
    clients: tuple[net.SignalingClient, ...],
    predicate,
    *,
    events: list[net.SignalingEvent] | None = None,
) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not predicate():
        server.poll()
        for client in clients:
            observed = client.poll()
            if events is not None:
                events.extend(observed)
        time.sleep(0.001)
    assert predicate()


def _connect(
    server: net.SignalingServer, client: net.SignalingClient
) -> list[net.SignalingEvent]:
    events: list[net.SignalingEvent] = []
    client.connect("127.0.0.1", port=server.port)
    _pump(
        server,
        (client,),
        lambda: any(
            event.type is net.SignalingEventType.CONNECTED for event in events
        ),
        events=events,
    )
    return events


def test_room_code_and_endpoint_validation() -> None:
    assert net.normalize_room_code("abcd-2345") == "ABCD2345"
    code = net.generate_room_code()
    assert len(code) == 6
    assert net.normalize_room_code(code) == code
    with pytest.raises(ValueError, match="4 to 12"):
        net.normalize_room_code("O0I1")
    with pytest.raises(ValueError, match="numeric"):
        net.RoomEndpoint("ABCD", "localhost", 7777)
    with pytest.raises(ValueError, match="unspecified"):
        net.RoomEndpoint("ABCD", "0.0.0.0", 7777)

    ipv4 = net.RoomEndpoint.parse("ABCD", "127.0.0.1:7777")
    ipv6 = net.RoomEndpoint.parse("EFGH", "[::1]:8888")
    assert ipv4.connection_string == "127.0.0.1:7777"
    assert ipv6.connection_string == "[::1]:8888"


def test_self_hosted_directory_registers_resolves_and_cleans_disconnect() -> None:
    server = _server()
    host = net.SignalingClient()
    guest = net.SignalingClient()
    host_events = _connect(server, host)
    guest_events = _connect(server, guest)
    try:
        assert host.register("PLAY-234", "127.0.0.1:7777") is net.SendStatus.QUEUED
        _pump(
            server,
            (host, guest),
            lambda: any(
                event.type is net.SignalingEventType.REGISTERED
                for event in host_events
            ),
            events=host_events,
        )
        assert server.rooms == (
            net.RoomEndpoint("PLAY234", "127.0.0.1", 7777),
        )

        assert guest.resolve("play-234") is net.SendStatus.QUEUED
        _pump(
            server,
            (host, guest),
            lambda: any(
                event.type is net.SignalingEventType.RESOLVED
                for event in guest_events
            ),
            events=guest_events,
        )
        resolved = next(
            event
            for event in guest_events
            if event.type is net.SignalingEventType.RESOLVED
        )
        assert resolved.endpoint is not None
        assert resolved.endpoint.connection_string == "127.0.0.1:7777"

        host.close("room host left")
        _pump(server, (guest,), lambda: server.rooms == (), events=guest_events)
        assert guest.resolve("PLAY234") is net.SendStatus.QUEUED
        _pump(
            server,
            (guest,),
            lambda: any(
                event.type is net.SignalingEventType.NOT_FOUND
                for event in guest_events
            ),
            events=guest_events,
        )
    finally:
        host.close()
        guest.close()
        server.stop()


def test_room_ownership_conflict_release_and_capacity_are_explicit() -> None:
    server = _server(max_rooms=1)
    first = net.SignalingClient()
    second = net.SignalingClient()
    first_events = _connect(server, first)
    second_events = _connect(server, second)
    try:
        first.register("RMM2", "127.0.0.1:7001")
        _pump(
            server,
            (first, second),
            lambda: any(
                event.type is net.SignalingEventType.REGISTERED
                for event in first_events
            ),
            events=first_events,
        )
        second.register("RMM2", "127.0.0.1:7002")
        second.register("RMM3", "127.0.0.1:7003")
        _pump(
            server,
            (first, second),
            lambda: sum(
                event.type is net.SignalingEventType.ERROR
                for event in second_events
            )
            == 2,
            events=second_events,
        )
        assert {event.reason for event in second_events if event.type is net.SignalingEventType.ERROR} == {
            "room code is already registered",
            "room directory is full",
        }

        first.release("RMM2")
        _pump(
            server,
            (first, second),
            lambda: any(
                event.type is net.SignalingEventType.RELEASED
                for event in first_events
            ),
            events=first_events,
        )
        assert server.rooms == ()
    finally:
        first.close()
        second.close()
        server.stop()
