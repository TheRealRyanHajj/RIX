"""Transport contracts and deterministic impairment simulation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntEnum
import math
import threading
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .scene import Scene
    from .scheduler import SchedulerStats

from ._easy3d import (
    NetworkError,
    _NetworkClient,
    _NetworkServer,
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


class ServerState(str, Enum):
    STOPPED = "stopped"
    LISTENING = "listening"


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
    SERVER_STOPPED = 1009
    SERVER_FULL = 1010


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


class Server:
    """Headless authoritative server with fixed-rate Python simulation.

    ``run`` never constructs a window, renderer, :class:`easy3d.Game`, SDL or
    bgfx device. Network and gameplay callbacks run synchronously on the thread
    calling ``run``, ``step`` or ``poll``. ``stop`` may be requested safely
    from another Python thread.
    """

    __slots__ = (
        "_native",
        "_scheduler",
        "_scene",
        "_running",
        "_stop_requested",
        "_stop_reason",
        "_callback_active",
        "_gameplay_thread_id",
        "_simulation_started",
        "_tick_count",
        "_max_catch_up_steps",
        "on_connect",
        "on_disconnect",
        "on_message",
        "__weakref__",
    )

    def __init__(
        self,
        *,
        port: int = 7777,
        max_players: int = 32,
        tick_rate: float = 60.0,
        bind_address: str = "0.0.0.0",
        handshake_timeout: float = 5.0,
        event_queue_capacity: int = 4096,
        maximum_message_size: int = 64 * 1024,
        protocol_version: int = 1,
        schema_version: int = 1,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
        on_connect: Callable[[Server, ConnectionId], None] | None = None,
        on_disconnect: Callable[[Server, NetworkEvent], None] | None = None,
        on_message: Callable[[Server, NetworkEvent], None] | None = None,
    ) -> None:
        if not isinstance(bind_address, str) or not bind_address:
            raise ValueError("bind_address must be a non-empty numeric address")
        integer_limits = (
            ("port", port, 0xFFFF),
            ("max_players", max_players, 1024),
            ("event_queue_capacity", event_queue_capacity, None),
            ("maximum_message_size", maximum_message_size, 1024 * 1024),
            ("protocol_version", protocol_version, 0xFFFF),
            ("schema_version", schema_version, 0xFFFF_FFFF),
            ("max_catch_up_steps", max_catch_up_steps, None),
        )
        for name, value, maximum in integer_limits:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0 or (maximum is not None and value > maximum):
                raise ValueError(f"{name} is outside its supported range")
        if (isinstance(handshake_timeout, bool) or
                not isinstance(handshake_timeout, (int, float))):
            raise TypeError("handshake_timeout must be a number")
        if not math.isfinite(float(handshake_timeout)) or handshake_timeout <= 0:
            raise ValueError("handshake_timeout must be finite and positive")
        for name, callback in (
            ("on_connect", on_connect),
            ("on_disconnect", on_disconnect),
            ("on_message", on_message),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")

        # SimulationScheduler owns the authoritative fixed-step and validates
        # tick_rate/fail-fast behavior without importing the graphical Game.
        from .scheduler import SimulationScheduler

        self._native = _NetworkServer(
            bind_address,
            port,
            max_players,
            float(handshake_timeout),
            event_queue_capacity,
            maximum_message_size,
            protocol_version,
            schema_version,
        )
        self._scheduler = SimulationScheduler(
            fixed_hz=tick_rate,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
        )
        self._scene: Scene | None = None
        self._running = False
        self._stop_requested = threading.Event()
        self._stop_reason = "server stopped"
        self._callback_active = False
        self._gameplay_thread_id = None
        self._simulation_started = False
        self._tick_count = 0
        self._max_catch_up_steps = max_catch_up_steps
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_message = on_message

    @property
    def state(self) -> ServerState:
        return ServerState(self._native.state)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def port(self) -> int:
        return self._native.port

    @property
    def bind_address(self) -> str:
        return self._native.bind_address

    @property
    def connections(self) -> tuple[ConnectionId, ...]:
        return tuple(ConnectionId(value) for value in self._native.connections)

    @property
    def scene(self) -> Scene | None:
        return self._scene

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def scheduler_stats(self) -> SchedulerStats:
        return self._scheduler.stats

    @property
    def script_errors(self) -> tuple[str, ...]:
        return self._scheduler.errors

    @property
    def stats(self) -> NetworkStats:
        return NetworkStats(*self._native.stats)

    def start(self) -> None:
        """Bind the native listener without starting the simulation loop."""

        if self.state is ServerState.LISTENING:
            raise NetworkError("network server is already listening")
        self._native.start()
        self._stop_requested.clear()
        self._stop_reason = "server stopped"
        self._simulation_started = False
        self._tick_count = 0

    def stop(self, reason: str = "server stopped") -> None:
        """Request loop shutdown; safe to call from another Python thread."""

        if not isinstance(reason, str):
            raise TypeError("server stop reason must be a string")
        if len(reason.encode("utf-8")) > 120 or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in reason
        ):
            raise ValueError("server stop reason must be at most 120 bytes without controls")
        self._stop_reason = reason or "server stopped"
        self._stop_requested.set()
        if not self._running and self.state is ServerState.LISTENING:
            self._native.stop(self._stop_reason)
            self._dispatch_events(self._native.poll(4096))
            self._simulation_started = False

    def load_scene(self, scene: Scene) -> None:
        from .scene import Scene

        if not isinstance(scene, Scene):
            raise TypeError("scene must be an easy3d.Scene")
        if self._running:
            raise RuntimeError("cannot replace the active scene while Server is running")
        if self._scene is scene:
            return
        scene._attach(self)
        previous = self._scene
        self._scene = scene
        if previous is not None:
            previous._detach(self)

    def unload_scene(self, *, clear: bool = False) -> Scene | None:
        scene = self._scene
        if scene is None:
            return None
        if self._running:
            raise RuntimeError("cannot unload the active scene while Server is running")
        if clear:
            scene.clear()
        scene._detach(self)
        self._scene = None
        return scene

    def send(
        self,
        connection: ConnectionId,
        payload: bytes | bytearray | memoryview,
        *,
        delivery: Delivery = Delivery.RELIABLE,
    ) -> SendStatus:
        if not isinstance(connection, ConnectionId):
            raise TypeError("connection must be an easy3d.network.ConnectionId")
        if not isinstance(delivery, Delivery):
            raise TypeError("delivery must be easy3d.network.Delivery")
        try:
            data = bytes(payload)
        except (TypeError, ValueError) as error:
            raise TypeError("network payload must be bytes-like") from error
        return SendStatus(
            self._native.send(connection.value, data, delivery.value)
        )

    def broadcast(
        self,
        payload: bytes | bytearray | memoryview,
        *,
        delivery: Delivery = Delivery.RELIABLE,
    ) -> dict[ConnectionId, SendStatus]:
        return {
            connection: self.send(connection, payload, delivery=delivery)
            for connection in self.connections
        }

    def disconnect(self, connection: ConnectionId, reason: str = "") -> None:
        if not isinstance(connection, ConnectionId):
            raise TypeError("connection must be an easy3d.network.ConnectionId")
        if not isinstance(reason, str):
            raise TypeError("disconnect reason must be a string")
        self._native.disconnect(connection.value, reason)

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        if isinstance(maximum_events, bool) or not isinstance(maximum_events, int):
            raise TypeError("maximum_events must be an integer")
        if maximum_events <= 0:
            raise ValueError("maximum_events must be positive")
        temporary_owner = self._gameplay_thread_id is None
        if temporary_owner:
            self._gameplay_thread_id = threading.get_ident()
        self._callback_active = True
        try:
            return self._dispatch_events(self._native.poll(maximum_events))
        finally:
            self._callback_active = False
            if temporary_owner:
                self._gameplay_thread_id = None

    def step(self) -> tuple[NetworkEvent, ...]:
        """Pump networking and execute exactly one authoritative fixed tick."""

        if self._running and self._gameplay_thread_id != threading.get_ident():
            raise RuntimeError("cannot step Server from outside its run thread")
        if self.state is ServerState.STOPPED:
            self.start()
        if not self._simulation_started:
            self._scheduler.begin_run()
            self._simulation_started = True
        temporary_owner = self._gameplay_thread_id is None
        if temporary_owner:
            self._gameplay_thread_id = threading.get_ident()
        self._callback_active = True
        try:
            events = self._dispatch_events(self._native.poll(256))
            self._scheduler.advance(self._scene, self._scheduler.fixed_dt)
            self._tick_count += 1
            return events
        finally:
            self._callback_active = False
            if temporary_owner:
                self._gameplay_thread_id = None

    def run(self) -> None:
        """Run the paced headless simulation until :meth:`stop` is requested."""

        if self._running:
            raise RuntimeError("this Server is already running")
        if self.state is ServerState.STOPPED:
            self.start()
        self._scheduler.begin_run()
        self._simulation_started = True
        self._running = True
        self._gameplay_thread_id = threading.get_ident()
        self._stop_requested.clear()
        next_tick = time.perf_counter()
        try:
            while not self._stop_requested.is_set():
                now = time.perf_counter()
                remaining = next_tick - now
                if remaining > 0:
                    self._stop_requested.wait(remaining)
                    continue
                catch_up_steps = 0
                while (
                    not self._stop_requested.is_set()
                    and now >= next_tick
                    and catch_up_steps < self._max_catch_up_steps
                ):
                    self.step()
                    next_tick += self._scheduler.fixed_dt
                    catch_up_steps += 1
                    now = time.perf_counter()
                if now >= next_tick:
                    next_tick = now + self._scheduler.fixed_dt
        finally:
            self._callback_active = True
            try:
                if self.state is ServerState.LISTENING:
                    self._native.stop(self._stop_reason)
                    self._dispatch_events(self._native.poll(4096))
                if self._scene is not None:
                    self._scene._commit_deferred(self._scheduler.destroy_callback)
            finally:
                self._callback_active = False
                self._running = False
                self._gameplay_thread_id = None
                self._simulation_started = False

    def _dispatch_events(self, values) -> tuple[NetworkEvent, ...]:  # type: ignore[no-untyped-def]
        events = tuple(_network_event(value) for value in values)
        for event in events:
            if event.type is EventType.CONNECTED and self.on_connect is not None:
                self.on_connect(self, event.connection)
            elif event.type is EventType.MESSAGE and self.on_message is not None:
                self.on_message(self, event)
            elif (
                event.type is EventType.DISCONNECTED
                and self.on_disconnect is not None
            ):
                self.on_disconnect(self, event)
        return events

    def _allows_scene_mutation(self, scene: Scene) -> bool:
        return (
            scene is self._scene
            and self._callback_active
            and self._gameplay_thread_id == threading.get_ident()
        )

    def _on_entity_destroyed(self, entity: object) -> None:
        self._scheduler.forget(entity)  # type: ignore[arg-type]


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
    "Server",
    "ServerState",
    "SimulatedEndpoint",
    "SimulatedLink",
    "backend_info",
    "backend_smoke_test",
]
