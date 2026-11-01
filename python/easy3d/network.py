"""Transport contracts and deterministic impairment simulation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntEnum
import math
from typing import Protocol, runtime_checkable

from ._easy3d import (
    NetworkError,
    _NetworkClient,
    _network_backend_info,
    _network_backend_smoke_test,
    _NetworkSimulator,
)


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


class ClientState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    HANDSHAKING = "handshaking"
    CONNECTED = "connected"


class DisconnectCode(IntEnum):
    NONE = 0
    NORMAL = 1
    MALFORMED_MESSAGE = 1000
    PROTOCOL_VERSION_MISMATCH = 1001
    SCHEMA_VERSION_MISMATCH = 1002
    ROLE_MISMATCH = 1003
    LIMIT_VIOLATION = 1004
    UNEXPECTED_MESSAGE = 1005
    MESSAGE_TOO_LARGE = 1006
    CONNECTION_TIMEOUT = 1007
    TRANSPORT_FAILURE = 1008


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
    disconnect_code: int = 0


@dataclass(frozen=True, slots=True)
class NetworkStats:
    messages_sent: int
    messages_received: int
    messages_lost: int
    bytes_sent: int
    bytes_received: int
    queue_rejections: int
    event_overflows: int


@dataclass(frozen=True, slots=True)
class ClientMetrics:
    state: ClientState
    ping_milliseconds: int
    outgoing_bytes_per_second: float
    incoming_bytes_per_second: float
    pending_reliable_bytes: int
    pending_unreliable_bytes: int
    negotiated_maximum_message_size: int
    transport: NetworkStats


@dataclass(frozen=True, slots=True)
class NetworkBackendInfo:
    available: bool
    name: str
    version: str
    crypto_provider: str


def backend_info() -> NetworkBackendInfo:
    """Return build-time native backend metadata without starting it."""

    return NetworkBackendInfo(*_network_backend_info())


def backend_smoke_test() -> bool:
    """Initialize the native backend and reliably round-trip a loopback message."""

    return _network_backend_smoke_test()


def _network_event(
    value: tuple[str, int, str, bytes, str, int, int],
) -> NetworkEvent:
    event_type, connection, delivery, payload, reason, sequence, code = value
    try:
        disconnect_code: int = DisconnectCode(code)
    except ValueError:
        # Preserve backend/OS reason codes outside Easy3D's stable app range.
        disconnect_code = code
    return NetworkEvent(
        EventType(event_type),
        ConnectionId(connection),
        Delivery(delivery),
        payload,
        reason,
        sequence,
        disconnect_code,
    )


@runtime_checkable
class NetworkTransport(Protocol):
    @property
    def connection(self) -> ConnectionId | None: ...

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


class Client:
    """Asynchronous direct-IP client driven by :meth:`poll`.

    Native connection callbacks only queue state. Optional Python callbacks are
    invoked synchronously by ``poll`` on its calling thread.
    """

    __slots__ = ("_native", "on_connect", "on_disconnect")

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        event_queue_capacity: int = 1024,
        maximum_message_size: int = 64 * 1024,
        protocol_version: int = 1,
        schema_version: int = 1,
        on_connect: Callable[[Client], None] | None = None,
        on_disconnect: Callable[[Client, NetworkEvent], None] | None = None,
    ) -> None:
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise TypeError("timeout must be a number")
        if not math.isfinite(float(timeout)) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        limits = (
            ("event_queue_capacity", event_queue_capacity, None),
            ("maximum_message_size", maximum_message_size, 1024 * 1024),
            ("protocol_version", protocol_version, 0xFFFF),
            ("schema_version", schema_version, 0xFFFF_FFFF),
        )
        for name, value, maximum in limits:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0 or (maximum is not None and value > maximum):
                raise ValueError(f"{name} is outside its supported range")
        if on_connect is not None and not callable(on_connect):
            raise TypeError("on_connect must be callable")
        if on_disconnect is not None and not callable(on_disconnect):
            raise TypeError("on_disconnect must be callable")
        self._native = _NetworkClient(
            float(timeout),
            event_queue_capacity,
            maximum_message_size,
            protocol_version,
            schema_version,
        )
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect

    def connect(self, address: str, port: int) -> None:
        if not isinstance(address, str):
            raise TypeError("address must be a string")
        if isinstance(port, bool) or not isinstance(port, int):
            raise TypeError("port must be an integer")
        if not 1 <= port <= 0xFFFF:
            raise ValueError("port must be between 1 and 65535")
        self._native.connect(address, port)

    @property
    def state(self) -> ClientState:
        return ClientState(self._native.state)

    @property
    def connection(self) -> ConnectionId | None:
        value = self._native.connection
        return ConnectionId(value) if value else None

    @property
    def remote_address(self) -> str:
        return self._native.remote_address

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
        connection = self.connection
        if connection is None:
            return SendStatus.INVALID_CONNECTION
        return SendStatus(
            self._native.send(connection.value, data, delivery.value)
        )

    def disconnect(self, reason: str = "") -> None:
        if not isinstance(reason, str):
            raise TypeError("disconnect reason must be a string")
        connection = self.connection
        if connection is None:
            raise NetworkError("network client is not active")
        self._native.disconnect(connection.value, reason)

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        if isinstance(maximum_events, bool) or not isinstance(maximum_events, int):
            raise TypeError("maximum_events must be an integer")
        if maximum_events <= 0:
            raise ValueError("maximum_events must be positive")
        events = tuple(
            _network_event(value)
            for value in self._native.poll(maximum_events)
        )
        for event in events:
            if event.type is EventType.CONNECTED and self.on_connect is not None:
                self.on_connect(self)
            elif (
                event.type is EventType.DISCONNECTED
                and self.on_disconnect is not None
            ):
                self.on_disconnect(self, event)
        return events

    @property
    def stats(self) -> NetworkStats:
        return NetworkStats(*self._native.stats)

    @property
    def metrics(self) -> ClientMetrics:
        (
            state,
            ping,
            outgoing,
            incoming,
            pending_reliable,
            pending_unreliable,
            maximum_message_size,
            stats,
        ) = self._native.metrics
        return ClientMetrics(
            ClientState(state),
            ping,
            outgoing,
            incoming,
            pending_reliable,
            pending_unreliable,
            maximum_message_size,
            NetworkStats(*stats),
        )


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
            _network_event(value)
            for value in self._link._native.poll(self._first, maximum_events)
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
    "Client",
    "ClientMetrics",
    "ClientState",
    "ConnectionId",
    "Delivery",
    "DisconnectCode",
    "EventType",
    "NetworkEvent",
    "NetworkError",
    "NetworkBackendInfo",
    "NetworkStats",
    "NetworkTransport",
    "SendStatus",
    "SimulatedEndpoint",
    "SimulatedLink",
    "backend_info",
    "backend_smoke_test",
]
