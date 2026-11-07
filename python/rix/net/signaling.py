"""Optional self-hosted room-code directory over the native RIX transport."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ipaddress
import secrets

from .._rix import NetworkError
from .messages import decode_message, encode_message
from .session import _address
from .transport import (
    Client,
    ClientState,
    ConnectionId,
    EventType,
    NetworkEvent,
    SendStatus,
    Server,
    ServerState,
)


_SCHEMA_VERSION = 0x5249_5853
_MAXIMUM_MESSAGE_SIZE = 2048
_ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_REGISTER = "rix.signal.register"
_REGISTERED = "rix.signal.registered"
_RESOLVE = "rix.signal.resolve"
_RESOLVED = "rix.signal.resolved"
_NOT_FOUND = "rix.signal.not_found"
_RELEASE = "rix.signal.release"
_RELEASED = "rix.signal.released"
_ERROR = "rix.signal.error"


def normalize_room_code(value: str) -> str:
    """Return a canonical 4–12 character unambiguous room code."""

    if not isinstance(value, str):
        raise TypeError("room code must be a string")
    normalized = value.strip().upper().replace("-", "")
    if not 4 <= len(normalized) <= 12 or any(
        character not in _ROOM_ALPHABET for character in normalized
    ):
        raise ValueError(
            "room code must contain 4 to 12 unambiguous ASCII letters/digits"
        )
    return normalized


def generate_room_code(length: int = 6) -> str:
    """Generate a cryptographically random, human-readable room code."""

    if isinstance(length, bool) or not isinstance(length, int):
        raise TypeError("room code length must be an integer")
    if not 4 <= length <= 12:
        raise ValueError("room code length must be in [4, 12]")
    return "".join(secrets.choice(_ROOM_ALPHABET) for _ in range(length))


def _numeric_address(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("endpoint address must be a non-empty numeric IP address")
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError("endpoint address must be a numeric IPv4 or IPv6 address") from error
    if parsed.is_unspecified or parsed.is_multicast:
        raise ValueError("endpoint address cannot be unspecified or multicast")
    return parsed.compressed


@dataclass(frozen=True, slots=True)
class RoomEndpoint:
    """One direct game endpoint advertised under a room code."""

    room_code: str
    address: str
    port: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "room_code", normalize_room_code(self.room_code))
        object.__setattr__(self, "address", _numeric_address(self.address))
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("endpoint port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("endpoint port must be in [1, 65535]")

    @property
    def connection_string(self) -> str:
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{host}:{self.port}"

    @classmethod
    def parse(cls, room_code: str, endpoint: str, *, port: int | None = None) -> RoomEndpoint:
        if port is None:
            address, parsed_port = _address(endpoint)
        else:
            address, parsed_port = endpoint, port
        return cls(room_code, address, parsed_port)


class SignalingEventType(str, Enum):
    CONNECTED = "connected"
    REGISTERED = "registered"
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    RELEASED = "released"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class SignalingEvent:
    type: SignalingEventType
    room_code: str = ""
    endpoint: RoomEndpoint | None = None
    reason: str = ""


class SignalingServer:
    """Headless self-hosted room directory; this is not a packet relay."""

    __slots__ = ("_server", "_max_rooms", "_rooms", "_owned")

    def __init__(
        self,
        *,
        port: int = 7790,
        bind_address: str = "0.0.0.0",
        max_clients: int = 1024,
        max_rooms: int = 4096,
        peer_timeout: float = 30.0,
    ) -> None:
        if isinstance(max_rooms, bool) or not isinstance(max_rooms, int):
            raise TypeError("max_rooms must be an integer")
        if not 1 <= max_rooms <= 65536:
            raise ValueError("max_rooms must be in [1, 65536]")
        self._max_rooms = max_rooms
        self._rooms: dict[str, tuple[ConnectionId, RoomEndpoint]] = {}
        self._owned: dict[ConnectionId, set[str]] = {}
        self._server = Server(
            port=port,
            max_players=max_clients,
            bind_address=bind_address,
            peer_timeout=peer_timeout,
            maximum_message_size=_MAXIMUM_MESSAGE_SIZE,
            schema_version=_SCHEMA_VERSION,
            on_disconnect=self._disconnected,
            on_message=self._message,
        )

    @property
    def port(self) -> int:
        return self._server.port

    @property
    def bind_address(self) -> str:
        return self._server.bind_address

    @property
    def state(self) -> ServerState:
        return self._server.state

    @property
    def rooms(self) -> tuple[RoomEndpoint, ...]:
        return tuple(
            endpoint
            for _owner, endpoint in sorted(
                self._rooms.values(), key=lambda item: item[1].room_code
            )
        )

    def start(self) -> None:
        self._server.start()

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        return self._server.poll(maximum_events)

    def run(self) -> None:
        self._server.run()

    def stop(self, reason: str = "signaling server stopped") -> None:
        try:
            self._server.stop(reason)
        finally:
            self._rooms.clear()
            self._owned.clear()

    def _send(self, connection: ConnectionId, name: str, **fields: object) -> None:
        status = self._server.send(
            connection,
            encode_message(
                name,
                fields,
                maximum_size=_MAXIMUM_MESSAGE_SIZE,
            ),
        )
        if status is not SendStatus.QUEUED:
            self._server.disconnect(connection, "signaling response backpressure")

    def _message(self, server: Server, event: NetworkEvent) -> None:
        try:
            message = decode_message(
                event.payload,
                maximum_size=_MAXIMUM_MESSAGE_SIZE,
            )
            fields = message.fields
            if message.name == _REGISTER:
                if set(fields) != {"room", "address", "port"}:
                    raise ValueError("register fields do not match the schema")
                endpoint = RoomEndpoint(
                    fields["room"],  # type: ignore[arg-type]
                    fields["address"],  # type: ignore[arg-type]
                    fields["port"],  # type: ignore[arg-type]
                )
                existing = self._rooms.get(endpoint.room_code)
                if existing is not None and existing[0] != event.connection:
                    self._send(
                        event.connection,
                        _ERROR,
                        room=endpoint.room_code,
                        reason="room code is already registered",
                    )
                    return
                if existing is None and len(self._rooms) >= self._max_rooms:
                    self._send(
                        event.connection,
                        _ERROR,
                        room=endpoint.room_code,
                        reason="room directory is full",
                    )
                    return
                self._rooms[endpoint.room_code] = (event.connection, endpoint)
                self._owned.setdefault(event.connection, set()).add(endpoint.room_code)
                self._send(
                    event.connection,
                    _REGISTERED,
                    room=endpoint.room_code,
                    address=endpoint.address,
                    port=endpoint.port,
                )
                return
            if message.name == _RESOLVE:
                if set(fields) != {"room"}:
                    raise ValueError("resolve fields do not match the schema")
                room = normalize_room_code(fields["room"])  # type: ignore[arg-type]
                existing = self._rooms.get(room)
                if existing is None:
                    self._send(event.connection, _NOT_FOUND, room=room)
                else:
                    endpoint = existing[1]
                    self._send(
                        event.connection,
                        _RESOLVED,
                        room=room,
                        address=endpoint.address,
                        port=endpoint.port,
                    )
                return
            if message.name == _RELEASE:
                if set(fields) != {"room"}:
                    raise ValueError("release fields do not match the schema")
                room = normalize_room_code(fields["room"])  # type: ignore[arg-type]
                existing = self._rooms.get(room)
                if existing is None or existing[0] != event.connection:
                    self._send(
                        event.connection,
                        _ERROR,
                        room=room,
                        reason="room is not owned by this connection",
                    )
                    return
                del self._rooms[room]
                self._owned.get(event.connection, set()).discard(room)
                self._send(event.connection, _RELEASED, room=room)
                return
            raise ValueError("unknown signaling request")
        except (TypeError, ValueError) as error:
            server.disconnect(event.connection, f"invalid signaling request: {error}")

    def _disconnected(self, _server: Server, event: NetworkEvent) -> None:
        for room in self._owned.pop(event.connection, set()):
            existing = self._rooms.get(room)
            if existing is not None and existing[0] == event.connection:
                del self._rooms[room]


class SignalingClient:
    """Nonblocking client for a self-hosted :class:`SignalingServer`."""

    __slots__ = ("_client",)

    def __init__(self, *, timeout: float = 5.0, peer_timeout: float = 30.0) -> None:
        self._client = Client(
            timeout=timeout,
            peer_timeout=peer_timeout,
            maximum_message_size=_MAXIMUM_MESSAGE_SIZE,
            schema_version=_SCHEMA_VERSION,
        )

    @property
    def state(self) -> ClientState:
        return self._client.state

    @property
    def is_connected(self) -> bool:
        return self.state is ClientState.CONNECTED

    def connect(self, address: str, *, port: int | None = None) -> None:
        host, parsed_port = _address(address, 7790)
        if port is not None:
            if isinstance(port, bool) or not isinstance(port, int):
                raise TypeError("port must be an integer")
            if not 1 <= port <= 65535:
                raise ValueError("port must be in [1, 65535]")
            parsed_port = port
        self._client.connect(host, parsed_port)

    def register(
        self,
        room_code: str,
        endpoint: str | RoomEndpoint,
        *,
        port: int | None = None,
    ) -> SendStatus:
        self._require_connected()
        parsed = (
            endpoint
            if isinstance(endpoint, RoomEndpoint)
            else RoomEndpoint.parse(room_code, endpoint, port=port)
        )
        room = normalize_room_code(room_code)
        if parsed.room_code != room:
            raise ValueError("endpoint room code does not match room_code")
        return self._send(
            _REGISTER,
            room=room,
            address=parsed.address,
            port=parsed.port,
        )

    def resolve(self, room_code: str) -> SendStatus:
        self._require_connected()
        return self._send(_RESOLVE, room=normalize_room_code(room_code))

    def release(self, room_code: str) -> SendStatus:
        self._require_connected()
        return self._send(_RELEASE, room=normalize_room_code(room_code))

    def poll(self, maximum_events: int = 256) -> tuple[SignalingEvent, ...]:
        result: list[SignalingEvent] = []
        for event in self._client.poll(maximum_events):
            if event.type is EventType.CONNECTED:
                result.append(SignalingEvent(SignalingEventType.CONNECTED))
            elif event.type is EventType.DISCONNECTED:
                result.append(
                    SignalingEvent(
                        SignalingEventType.DISCONNECTED,
                        reason=event.reason,
                    )
                )
            elif event.type is EventType.MESSAGE:
                try:
                    result.append(self._response(event.payload))
                except (TypeError, ValueError) as error:
                    self._client.disconnect("invalid signaling response")
                    raise NetworkError(
                        f"received invalid signaling response: {error}"
                    ) from error
        return tuple(result)

    def close(self, reason: str = "signaling client closed") -> None:
        if self._client.connection is not None:
            self._client.disconnect(reason)
            self._client.poll()

    def _send(self, name: str, **fields: object) -> SendStatus:
        return self._client.send(
            encode_message(name, fields, maximum_size=_MAXIMUM_MESSAGE_SIZE)
        )

    def _response(self, payload: bytes) -> SignalingEvent:
        message = decode_message(payload, maximum_size=_MAXIMUM_MESSAGE_SIZE)
        fields = message.fields
        if message.name in (_REGISTERED, _RESOLVED):
            if set(fields) != {"room", "address", "port"}:
                raise ValueError("endpoint response fields do not match the schema")
            endpoint = RoomEndpoint(
                fields["room"],  # type: ignore[arg-type]
                fields["address"],  # type: ignore[arg-type]
                fields["port"],  # type: ignore[arg-type]
            )
            event_type = (
                SignalingEventType.REGISTERED
                if message.name == _REGISTERED
                else SignalingEventType.RESOLVED
            )
            return SignalingEvent(event_type, endpoint.room_code, endpoint)
        if message.name in (_NOT_FOUND, _RELEASED):
            if set(fields) != {"room"}:
                raise ValueError("room response fields do not match the schema")
            room = normalize_room_code(fields["room"])  # type: ignore[arg-type]
            event_type = (
                SignalingEventType.NOT_FOUND
                if message.name == _NOT_FOUND
                else SignalingEventType.RELEASED
            )
            return SignalingEvent(event_type, room)
        if message.name == _ERROR:
            if set(fields) != {"room", "reason"} or not isinstance(
                fields["reason"], str
            ):
                raise ValueError("error response fields do not match the schema")
            return SignalingEvent(
                SignalingEventType.ERROR,
                normalize_room_code(fields["room"]),  # type: ignore[arg-type]
                reason=fields["reason"],
            )
        raise ValueError("unknown signaling response")

    def _require_connected(self) -> None:
        if not self.is_connected:
            raise NetworkError("signaling client is not connected")

    def __enter__(self) -> SignalingClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "RoomEndpoint",
    "SignalingClient",
    "SignalingEvent",
    "SignalingEventType",
    "SignalingServer",
    "generate_room_code",
    "normalize_room_code",
]
