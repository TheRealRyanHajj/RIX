from __future__ import annotations

import pytest

from easy3d import NetworkError, network


def _connected(link: network.SimulatedLink) -> None:
    first = link.first.poll()
    second = link.second.poll()
    assert tuple(event.type for event in first) == (network.EventType.CONNECTED,)
    assert tuple(event.type for event in second) == (network.EventType.CONNECTED,)


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
    assert limited.first.poll()[0].reason == "test complete"
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
