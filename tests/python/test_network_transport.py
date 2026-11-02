from __future__ import annotations

import time

import pytest

from easy3d import NetworkError, network


def _connected(link: network.SimulatedLink) -> None:
    first = link.first.poll()
    second = link.second.poll()
    assert tuple(event.type for event in first) == (network.EventType.CONNECTED,)
    assert tuple(event.type for event in second) == (network.EventType.CONNECTED,)


def test_native_backend_metadata_and_loopback_smoke() -> None:
    assert network.backend_info() == network.NetworkBackendInfo(
        True,
        "GameNetworkingSockets",
        "1.6.1",
        "Windows BCrypt",
    )
    assert network.backend_smoke_test()


def test_direct_ip_client_validation_metrics_and_timeout_callback() -> None:
    disconnected: list[network.NetworkEvent] = []
    connected: list[network.Client] = []
    client = network.Client(
        timeout=0.02,
        on_connect=connected.append,
        on_disconnect=lambda _client, event: disconnected.append(event),
    )
    assert isinstance(client, network.NetworkTransport)
    assert client.state is network.ClientState.DISCONNECTED
    assert client.connection is None
    assert client.send(b"inactive") is network.SendStatus.INVALID_CONNECTION
    assert client.metrics == network.ClientMetrics(
        network.ClientState.DISCONNECTED,
        -1,
        0.0,
        0.0,
        0,
        0,
        0,
        network.NetworkStats(0, 0, 0, 0, 0, 0, 0),
    )
    with pytest.raises(ValueError, match="port"):
        client.connect("127.0.0.1", 0)
    with pytest.raises(ValueError, match="numeric"):
        client.connect("not-an-ip", 32100)
    with pytest.raises(NetworkError, match="not active"):
        client.disconnect()

    # Port 1 is intentionally not an Easy3D listener. An immediate transport
    # refusal or the client-owned 20 ms handshake deadline are both valid; in
    # either case poll dispatches one typed failure callback on this thread.
    client.connect("127.0.0.1", 1)
    deadline = time.monotonic() + 1.0
    observed: tuple[network.NetworkEvent, ...] = ()
    while time.monotonic() < deadline and not observed:
        observed = client.poll()
        time.sleep(0.002)
    assert len(observed) == 1
    assert observed[0].type is network.EventType.DISCONNECTED
    assert observed[0].disconnect_code != network.DisconnectCode.NONE
    assert disconnected == [observed[0]]
    assert connected == []
    assert client.state is network.ClientState.DISCONNECTED
    assert client.connection is None


@pytest.mark.parametrize(
    "arguments",
    [
        {"timeout": 0},
        {"timeout": float("inf")},
        {"peer_timeout": 0},
        {"peer_timeout": float("inf")},
        {"event_queue_capacity": 0},
        {"maximum_message_size": 1024 * 1024 + 1},
        {"protocol_version": True},
        {"schema_version": 1 << 32},
        {"on_connect": 42},
    ],
)
def test_direct_ip_client_rejects_invalid_configuration(
    arguments: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        network.Client(**arguments)  # type: ignore[arg-type]


def test_simulated_link_preserves_latency_order_and_metadata() -> None:
    link = network.SimulatedLink(
        latency=0.05,
        seed=7,
        queue_capacity=2,
        maximum_message_size=8,
    )
    assert isinstance(link.first, network.NetworkTransport)
    assert link.first.connection != link.second.connection
    _connected(link)

    assert link.first.send(b"hello") is network.SendStatus.QUEUED
    assert (
        link.first.send(b"world", delivery=network.Delivery.UNRELIABLE)
        is network.SendStatus.QUEUED
    )
    assert link.first.send(b"again") is network.SendStatus.QUEUE_FULL
    assert link.in_flight_count == 2

    link.advance(0.049)
    assert link.second.poll() == ()
    link.advance(0.001)
    events = link.second.poll()
    assert tuple(event.type for event in events) == (
        network.EventType.MESSAGE,
        network.EventType.MESSAGE,
    )
    assert tuple(event.payload for event in events) == (b"hello", b"world")
    assert tuple(event.delivery for event in events) == (
        network.Delivery.RELIABLE,
        network.Delivery.UNRELIABLE,
    )
    assert events[0].sequence < events[1].sequence
    assert events[0].connection == link.second.connection
    assert link.first.stats == network.NetworkStats(2, 0, 0, 10, 0, 1, 0)
    assert link.second.stats == network.NetworkStats(0, 2, 0, 0, 10, 0, 0)


def test_simulated_link_limits_loss_overflow_and_disconnect() -> None:
    loss = network.SimulatedLink(loss=1.0, seed=42)
    _connected(loss)
    assert loss.first.send(b"drop") is network.SendStatus.QUEUED
    loss.advance(0.0)
    assert loss.second.poll() == ()
    assert loss.first.stats.messages_lost == 1

    limited = network.SimulatedLink(maximum_message_size=3)
    _connected(limited)
    assert limited.first.send(b"four") is network.SendStatus.MESSAGE_TOO_LARGE
    limited.first.disconnect("test complete")
    disconnect = limited.first.poll()[0]
    assert disconnect.reason == "test complete"
    assert disconnect.disconnect_code is network.DisconnectCode.NORMAL
    assert limited.second.poll()[0].type is network.EventType.DISCONNECTED
    assert limited.first.send(b"x") is network.SendStatus.INVALID_CONNECTION

    overflow = network.SimulatedLink(
        queue_capacity=2, event_queue_capacity=1
    )
    _connected(overflow)
    assert overflow.first.send(b"a") is network.SendStatus.QUEUED
    assert overflow.first.send(b"b") is network.SendStatus.QUEUED
    overflow.advance(0.0)
    with pytest.raises(NetworkError, match="capacity exhausted"):
        overflow.second.poll()
    assert overflow.second.poll()[0].payload == b"a"
    assert overflow.second.stats.event_overflows == 1


def test_impairment_trace_is_reproducible_for_a_seed() -> None:
    def trace(seed: int) -> tuple[tuple[bytes, ...], network.NetworkStats]:
        link = network.SimulatedLink(
            latency=0.03,
            jitter=0.02,
            loss=0.35,
            seed=seed,
            queue_capacity=32,
        )
        _connected(link)
        for value in range(20):
            assert link.first.send(bytes([value])) is network.SendStatus.QUEUED
        received: list[bytes] = []
        for _ in range(10):
            link.advance(0.01)
            received.extend(event.payload for event in link.second.poll())
        return tuple(received), link.first.stats

    assert trace(99) == trace(99)


@pytest.mark.parametrize(
    ("arguments", "exception"),
    [
        ({"latency": -1}, ValueError),
        ({"jitter": float("nan")}, ValueError),
        ({"loss": 1.1}, ValueError),
        ({"queue_capacity": 0}, ValueError),
        ({"event_queue_capacity": True}, TypeError),
        ({"maximum_message_size": 0}, ValueError),
    ],
)
def test_simulated_link_rejects_invalid_configuration(
    arguments: dict[str, object], exception: type[Exception]
) -> None:
    with pytest.raises(exception):
        network.SimulatedLink(**arguments)  # type: ignore[arg-type]


def test_connection_and_endpoint_argument_validation() -> None:
    with pytest.raises(ValueError):
        network.ConnectionId(0)
    with pytest.raises(ValueError):
        network.ConnectionId(1 << 64)
    link = network.SimulatedLink()
    _connected(link)
    with pytest.raises(TypeError):
        link.first.send("text")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        link.first.send(b"x", delivery="reliable")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        link.first.poll(0)
    with pytest.raises(ValueError):
        link.advance(-0.1)
