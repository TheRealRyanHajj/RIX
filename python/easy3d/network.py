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


class ListenRole(str, Enum):
    AUTHORITY = "authority"
    CLIENT = "client"


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
class ListenEvent:
    """One event tagged with its isolated listen-host role."""

    role: ListenRole
    event: NetworkEvent
    local_host: bool


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


def _validated_peer_timeout(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError("peer_timeout must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0.001 <= result <= 2_147_483.647:
        raise ValueError("peer_timeout must be between 0.001 and 2147483.647")
    return result


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
        peer_timeout: float = 10.0,
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
        validated_peer_timeout = _validated_peer_timeout(peer_timeout)
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
            validated_peer_timeout,
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
        peer_timeout: float = 10.0,
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
        validated_peer_timeout = _validated_peer_timeout(peer_timeout)
        for name, callback in (
            ("on_connect", on_connect),
            ("on_disconnect", on_disconnect),
            ("on_message", on_message),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable")

        # SimulationScheduler owns the authoritative fixed-step and validates
        # tick_rate/fail-fast behavior without importing the graphical Game.
        from .scheduler import ScriptRole, SimulationScheduler

        self._native = _NetworkServer(
            bind_address,
            port,
            max_players,
            float(handshake_timeout),
            validated_peer_timeout,
            event_queue_capacity,
            maximum_message_size,
            protocol_version,
            schema_version,
        )
        self._scheduler = SimulationScheduler(
            fixed_hz=tick_rate,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
            role=ScriptRole.SERVER,
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

        self._run_loop()

    def _run_loop(self, after_tick: Callable[[], None] | None = None) -> None:
        """Internal paced owner used by dedicated and listen-server roles."""

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
                    if after_tick is not None:
                        after_tick()
                    next_tick += self._scheduler.fixed_dt
                    catch_up_steps += 1
                    now = time.perf_counter()
                if now >= next_tick:
                    next_tick = now + self._scheduler.fixed_dt
        finally:
            self._callback_active = True
            try:
                try:
                    if self.state is ServerState.LISTENING:
                        self._native.stop(self._stop_reason)
                        self._dispatch_events(self._native.poll(4096))
                        if after_tick is not None:
                            after_tick()
                finally:
                    if self._scene is not None:
                        self._scene._commit_deferred(
                            self._scheduler.destroy_callback
                        )
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


class ListenServer:
    """Compose an authoritative server and one isolated loopback client role.

    The authority is the only role allowed to own a scene or execute gameplay
    lifecycle callbacks. The local client uses the same real transport and
    handshake as a remote client; matching numeric connection IDs across the
    two role-local spaces have no shared identity meaning.
    """

    __slots__ = (
        "_authority",
        "_client",
        "_authority_connection",
        "_pending_events",
        "_starting",
        "_started",
        "_startup_timeout",
        "_local_address",
        "_suppress_callback",
        "on_event",
    )

    def __init__(
        self,
        *,
        port: int = 7777,
        max_players: int = 32,
        tick_rate: float = 60.0,
        bind_address: str = "0.0.0.0",
        local_address: str = "127.0.0.1",
        handshake_timeout: float = 5.0,
        peer_timeout: float = 10.0,
        event_queue_capacity: int = 4096,
        maximum_message_size: int = 64 * 1024,
        protocol_version: int = 1,
        schema_version: int = 1,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
        on_event: Callable[[ListenServer, ListenEvent], None] | None = None,
    ) -> None:
        if not isinstance(local_address, str) or not local_address:
            raise ValueError("local_address must be a non-empty numeric address")
        if on_event is not None and not callable(on_event):
            raise TypeError("on_event must be callable")
        self._authority_connection: ConnectionId | None = None
        self._pending_events: list[ListenEvent] = []
        self._starting = False
        self._started = False
        self._startup_timeout = float(handshake_timeout)
        self._suppress_callback = False
        self.on_event = on_event
        self._authority = Server(
            port=port,
            max_players=max_players,
            tick_rate=tick_rate,
            bind_address=bind_address,
            handshake_timeout=handshake_timeout,
            peer_timeout=peer_timeout,
            event_queue_capacity=event_queue_capacity,
            maximum_message_size=maximum_message_size,
            protocol_version=protocol_version,
            schema_version=schema_version,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
            on_connect=self._on_authority_connect,
            on_disconnect=self._on_authority_disconnect,
            on_message=self._on_authority_message,
        )
        self._client = Client(
            timeout=handshake_timeout,
            peer_timeout=peer_timeout,
            event_queue_capacity=event_queue_capacity,
            maximum_message_size=maximum_message_size,
            protocol_version=protocol_version,
            schema_version=schema_version,
            on_connect=self._on_client_connect,
            on_disconnect=self._on_client_disconnect,
        )
        # Kept after native validation so an invalid numeric address reports
        # through the same client contract during start().
        self._local_address = local_address

    @property
    def authority(self) -> Server:
        return self._authority

    @property
    def client(self) -> Client:
        return self._client

    @property
    def authority_connection(self) -> ConnectionId | None:
        return self._authority_connection

    @property
    def is_running(self) -> bool:
        return self._authority.is_running

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def port(self) -> int:
        return self._authority.port

    @property
    def scene(self) -> Scene | None:
        return self._authority.scene

    @property
    def tick_count(self) -> int:
        return self._authority.tick_count

    def load_scene(self, scene: Scene) -> None:
        self._authority.load_scene(scene)

    def unload_scene(self, *, clear: bool = False) -> Scene | None:
        return self._authority.unload_scene(clear=clear)

    def start(self) -> tuple[ListenEvent, ...]:
        """Bind and fully establish the private host client before returning."""

        if self._started or self._starting or self._authority.is_running:
            raise NetworkError("listen server is already active")
        self._pending_events.clear()
        startup_events: list[ListenEvent] = []
        self._starting = True
        try:
            self._authority.start()
            self._client.connect(self._local_address, self._authority.port)
            deadline = time.monotonic() + self._startup_timeout
            while time.monotonic() < deadline:
                startup_events.extend(self.poll())
                if (
                    self._authority_connection is not None
                    and self._client.state is ClientState.CONNECTED
                ):
                    self._started = True
                    return tuple(startup_events)
                if self._client.state is ClientState.DISCONNECTED:
                    break
                time.sleep(0.001)
            raise NetworkError("listen-server host connection did not establish")
        except BaseException:
            self._cleanup_failed_start()
            raise
        finally:
            self._starting = False

    def poll(self, maximum_events: int = 256) -> tuple[ListenEvent, ...]:
        if self._authority.state is ServerState.LISTENING:
            self._authority.poll(maximum_events)
        self._consume_client_messages(self._client.poll(maximum_events))
        return self._drain_pending()

    def step(self) -> tuple[ListenEvent, ...]:
        startup: tuple[ListenEvent, ...] = ()
        if not self._started:
            startup = self.start()
        self._authority.step()
        self._consume_client_messages(self._client.poll())
        return startup + self._drain_pending()

    def run(self) -> None:
        """Run one authoritative simulation with the local client pumped."""

        if not self._started:
            self.start()
        try:
            self._authority._run_loop(self._after_run_tick)
        finally:
            deadline = time.monotonic() + 0.25
            while (
                self._client.state is not ClientState.DISCONNECTED
                and time.monotonic() < deadline
            ):
                self._consume_client_messages(self._client.poll())
                self._pending_events.clear()
                time.sleep(0.001)
            self._started = False

    def stop(self, reason: str = "listen server stopped") -> tuple[ListenEvent, ...]:
        """Stop both roles; while running this is a thread-safe request."""

        if self._authority.is_running:
            self._authority.stop(reason)
            return ()
        if self._client.connection is not None:
            self._client.disconnect(reason)
            self._consume_client_messages(self._client.poll())
            deadline = time.monotonic() + 0.25
            while (
                self._authority_connection is not None
                and self._authority.state is ServerState.LISTENING
                and time.monotonic() < deadline
            ):
                self._authority.poll()
                time.sleep(0.001)
        if self._authority.state is ServerState.LISTENING:
            self._authority.stop(reason)
        self._started = False
        return self._drain_pending()

    def _record(
        self,
        role: ListenRole,
        event: NetworkEvent,
        *,
        local_host: bool,
    ) -> None:
        tagged = ListenEvent(role, event, local_host)
        self._pending_events.append(tagged)
        if self.on_event is not None and not self._suppress_callback:
            self.on_event(self, tagged)

    def _on_authority_connect(
        self, _server: Server, connection: ConnectionId
    ) -> None:
        if self._starting and self._authority_connection is None:
            self._authority_connection = connection
        event = NetworkEvent(EventType.CONNECTED, connection)
        self._record(
            ListenRole.AUTHORITY,
            event,
            local_host=connection == self._authority_connection,
        )

    def _on_authority_disconnect(
        self, _server: Server, event: NetworkEvent
    ) -> None:
        local_host = event.connection == self._authority_connection
        self._record(ListenRole.AUTHORITY, event, local_host=local_host)
        if local_host:
            self._authority_connection = None

    def _on_authority_message(self, _server: Server, event: NetworkEvent) -> None:
        self._record(
            ListenRole.AUTHORITY,
            event,
            local_host=event.connection == self._authority_connection,
        )

    def _on_client_connect(self, client: Client) -> None:
        connection = client.connection
        if connection is not None:
            self._record(
                ListenRole.CLIENT,
                NetworkEvent(EventType.CONNECTED, connection),
                local_host=True,
            )

    def _on_client_disconnect(self, _client: Client, event: NetworkEvent) -> None:
        self._record(ListenRole.CLIENT, event, local_host=True)
        self._started = False

    def _after_run_tick(self) -> None:
        self._consume_client_messages(self._client.poll())
        # During a blocking run events are synchronously observable through
        # on_event; do not retain an unbounded history for a later poll.
        self._pending_events.clear()

    def _cleanup_failed_start(self) -> None:
        self._suppress_callback = True
        try:
            try:
                if self._client.connection is not None:
                    self._client.disconnect("listen-server startup failed")
                    self._consume_client_messages(self._client.poll())
            finally:
                if self._authority.state is ServerState.LISTENING:
                    self._authority.stop("listen-server startup failed")
        finally:
            self._authority_connection = None
            self._started = False
            self._pending_events.clear()
            self._suppress_callback = False

    def _drain_pending(self) -> tuple[ListenEvent, ...]:
        events = tuple(self._pending_events)
        self._pending_events.clear()
        return events

    def _consume_client_messages(
        self, events: tuple[NetworkEvent, ...]
    ) -> None:
        for event in events:
            if event.type is EventType.MESSAGE:
                self._record(ListenRole.CLIENT, event, local_host=True)


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
    "ListenEvent",
    "ListenRole",
    "ListenServer",
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
