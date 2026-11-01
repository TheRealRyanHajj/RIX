"""Transport contracts and deterministic impairment simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol, runtime_checkable

from ._easy3d import NetworkError, _NetworkSimulator


class Delivery(str, Enum):
    RELIABLE = "reliable"
    UNRELIABLE = "unreliable"


class SendStatus(str, Enum):
    QUEUED = "queued"
    INVALID_CONNECTION = "invalid_connection"
    MESSAGE_TOO_LARGE = "message_too_large"
    QUEUE_FULL = "queue_full"


class EventType(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    MESSAGE = "message"


@dataclass(frozen=True, slots=True, order=True)
class ConnectionId:
    """Opaque process-local transport connection identity."""

    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or self.value <= 0
            or self.value > 0xFFFF_FFFF_FFFF_FFFF
        ):
            raise ValueError("connection ID must be an unsigned nonzero 64-bit integer")


@dataclass(frozen=True, slots=True)
class NetworkEvent:
    type: EventType
    connection: ConnectionId
    delivery: Delivery = Delivery.RELIABLE
    payload: bytes = b""
    reason: str = ""
    sequence: int = 0


@dataclass(frozen=True, slots=True)
class NetworkStats:
    messages_sent: int
    messages_received: int
    messages_lost: int
    bytes_sent: int
    bytes_received: int
    queue_rejections: int
    event_overflows: int


@runtime_checkable
class NetworkTransport(Protocol):
    @property
    def connection(self) -> ConnectionId: ...

    def send(
        self,
        payload: bytes | bytearray | memoryview,
        *,
        delivery: Delivery = Delivery.RELIABLE,
    ) -> SendStatus: ...

    def disconnect(self, reason: str = "") -> None: ...

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]: ...

    @property
    def stats(self) -> NetworkStats: ...


class SimulatedEndpoint:
    """One endpoint of a deterministic in-memory transport link."""

    __slots__ = ("_link", "_first", "_connection")

    def __init__(self, link: SimulatedLink, first: bool, connection: int) -> None:
        self._link = link
        self._first = first
        self._connection = ConnectionId(connection)

    @property
    def connection(self) -> ConnectionId:
        return self._connection

    def send(
        self,
        payload: bytes | bytearray | memoryview,
        *,
        delivery: Delivery = Delivery.RELIABLE,
    ) -> SendStatus:
        if not isinstance(delivery, Delivery):
            raise TypeError("delivery must be easy3d.network.Delivery")
        try:
            data = bytes(payload)
        except (TypeError, ValueError) as error:
            raise TypeError("network payload must be bytes-like") from error
        value = self._link._native.send(
            self._first, self.connection.value, data, delivery.value
        )
        return SendStatus(value)

    def disconnect(self, reason: str = "") -> None:
        if not isinstance(reason, str):
            raise TypeError("disconnect reason must be a string")
        self._link._native.disconnect(
            self._first, self.connection.value, reason
        )

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        if isinstance(maximum_events, bool) or not isinstance(maximum_events, int):
            raise TypeError("maximum_events must be an integer")
        if maximum_events <= 0:
            raise ValueError("maximum_events must be positive")
        return tuple(
            NetworkEvent(
                EventType(event_type),
                ConnectionId(connection),
                Delivery(delivery),
                payload,
                reason,
                sequence,
            )
            for event_type, connection, delivery, payload, reason, sequence in
            self._link._native.poll(self._first, maximum_events)
        )

    @property
    def stats(self) -> NetworkStats:
        return NetworkStats(*self._link._native.stats(self._first))


class SimulatedLink:
    """Two native transport endpoints with deterministic loss and delay.

    The simulator models a bounded datagram link, not reliable retransmission.
    Delivery intent is preserved as metadata for higher protocol layers.
    """

    __slots__ = ("_native", "first", "second")

    def __init__(
        self,
        *,
        latency: float = 0.0,
        jitter: float = 0.0,
        loss: float = 0.0,
        seed: int = 1,
        queue_capacity: int = 1024,
        event_queue_capacity: int = 1024,
        maximum_message_size: int = 64 * 1024,
    ) -> None:
        for name, value in (("latency", latency), ("jitter", jitter)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be a number")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not isinstance(loss, (int, float)) or isinstance(loss, bool):
            raise TypeError("loss must be a number")
        if not math.isfinite(float(loss)) or not 0 <= loss <= 1:
            raise ValueError("loss must be between zero and one")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        for name, value in (
            ("queue_capacity", queue_capacity),
            ("event_queue_capacity", event_queue_capacity),
            ("maximum_message_size", maximum_message_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        self._native = _NetworkSimulator(
            float(latency),
            float(jitter),
            float(loss),
            seed,
            queue_capacity,
            event_queue_capacity,
            maximum_message_size,
        )
        self.first = SimulatedEndpoint(
            self, True, self._native.first_connection
        )
        self.second = SimulatedEndpoint(
            self, False, self._native.second_connection
        )

    def advance(self, elapsed_seconds: float) -> None:
        if not isinstance(elapsed_seconds, (int, float)) or isinstance(
            elapsed_seconds, bool
        ):
            raise TypeError("elapsed_seconds must be a number")
        self._native.advance(float(elapsed_seconds))

    @property
    def time_seconds(self) -> float:
        return self._native.time_seconds

    @property
    def in_flight_count(self) -> int:
        return self._native.in_flight_count


__all__ = [
    "ConnectionId",
    "Delivery",
    "EventType",
    "NetworkEvent",
    "NetworkError",
    "NetworkStats",
    "NetworkTransport",
    "SendStatus",
    "SimulatedEndpoint",
    "SimulatedLink",
]
