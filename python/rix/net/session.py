"""Beginner-facing event sessions built on the native RIX transport."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._rix import NetworkError
from .messages import MessageSchema, decode_message, encode_message
from .transport import (
    Client,
    ConnectionId,
    Delivery,
    EventType,
    ListenEvent,
    ListenRole,
    ListenServer,
    NetworkEvent,
    SendStatus,
)


MessageHandler = Callable[..., None]


class SessionRole(str, Enum):
    CLOSED = "closed"
    CLIENT = "client"
    HOST = "host"


@dataclass(frozen=True, slots=True)
class Player:
    """Stable session-level identity supplied to application callbacks."""

    id: int
    local: bool = False
    server: bool = False


SERVER = Player(0, server=True)


def _address(value: str, default_port: int = 7777) -> tuple[str, int]:
    if not isinstance(value, str) or not value:
        raise ValueError("address must be a non-empty string")
    if value.startswith("["):
        end = value.find("]")
        if end < 0:
            raise ValueError("bracketed IPv6 address is missing ']'")
        host = value[1:end]
        suffix = value[end + 1 :]
        if not suffix:
            return host, default_port
        if not suffix.startswith(":"):
            raise ValueError("invalid bracketed address")
        port_text = suffix[1:]
    elif value.count(":") == 1:
        host, port_text = value.rsplit(":", 1)
    else:
        return value, default_port
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("address port must be an integer") from error
    if not host or not 1 <= port <= 65535:
        raise ValueError("address must contain a host and port in [1, 65535]")
    return host, port


class Session:
    """Optional nonblocking messaging for Pygame, RIX, or headless programs.

    Callbacks run only from :meth:`update` (or synchronously during
    :meth:`host` startup), never from a native transport worker thread.
    """

    __slots__ = (
        "_client",
        "_host",
        "_handlers",
        "_maximum_message_size",
        "_role",
        "_players",
        "_schemas",
    )

    def __init__(self, *, maximum_message_size: int = 64 * 1024) -> None:
        if isinstance(maximum_message_size, bool) or not isinstance(
            maximum_message_size, int
        ):
            raise TypeError("maximum_message_size must be an integer")
        if not 256 <= maximum_message_size <= 1024 * 1024:
            raise ValueError("maximum_message_size must be in [256, 1048576]")
        self._maximum_message_size = maximum_message_size
        self._client: Client | None = None
        self._host: ListenServer | None = None
        self._role = SessionRole.CLOSED
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._players: dict[int, Player] = {}
        self._schemas: dict[str, MessageSchema] = {}

    @property
    def role(self) -> SessionRole:
        return self._role

    @property
    def players(self) -> tuple[Player, ...]:
        return tuple(self._players.values())

    @property
    def is_open(self) -> bool:
        return self._role is not SessionRole.CLOSED

    def on(self, name: str) -> Callable[[MessageHandler], MessageHandler]:
        """Register a named message, ``connect``, or ``disconnect`` callback."""

        self._validate_handler_name(name)

        def register(callback: MessageHandler) -> MessageHandler:
            if not callable(callback):
                raise TypeError("message handler must be callable")
            bucket = self._handlers.setdefault(name, [])
            if callback in bucket:
                raise ValueError(f"handler is already registered for {name!r}")
            bucket.append(callback)
            return callback

        return register

    def off(self, name: str, callback: MessageHandler) -> bool:
        self._validate_handler_name(name)
        bucket = self._handlers.get(name)
        if bucket is None or callback not in bucket:
            return False
        bucket.remove(callback)
        if not bucket:
            del self._handlers[name]
        return True

    def register_message(
        self,
        name: str,
        /,
        *,
        allow_extra: bool = False,
        **fields: type | tuple[type, ...],
    ) -> MessageSchema:
        """Declare required runtime field types for one application message."""

        self._validate_message_name(name)
        if name in self._schemas:
            raise ValueError(f"message schema {name!r} is already registered")
        schema = MessageSchema.create(name, fields, allow_extra=allow_extra)
        self._schemas[name] = schema
        return schema

    def unregister_message(self, name: str) -> bool:
        self._validate_message_name(name)
        return self._schemas.pop(name, None) is not None

    def host(
        self,
        *,
        port: int = 7777,
        max_players: int = 32,
        tick_rate: float = 60.0,
        bind_address: str = "0.0.0.0",
        local_address: str = "127.0.0.1",
    ) -> None:
        """Start a listen server with a separate logical local client."""

        self._require_closed()
        host = ListenServer(
            port=port,
            max_players=max_players,
            tick_rate=tick_rate,
            bind_address=bind_address,
            local_address=local_address,
            maximum_message_size=self._maximum_message_size,
        )
        try:
            startup = host.start()
        except BaseException:
            host.stop("session startup failed")
            raise
        self._host = host
        self._role = SessionRole.HOST
        try:
            for event in startup:
                self._handle_listen_event(event)
        except BaseException:
            # A lifecycle callback is application code and may fail. Startup
            # must remain transactional: never leave a listening native
            # transport hidden behind a Session whose host() call raised.
            try:
                host.stop("session startup callback failed")
            finally:
                self._host = None
                self._client = None
                self._players.clear()
                self._role = SessionRole.CLOSED
            raise

    def join(self, address: str, *, port: int | None = None) -> None:
        """Begin a nonblocking direct-IP connection to a server."""

        self._require_closed()
        host, parsed_port = _address(address)
        if port is not None:
            if isinstance(port, bool) or not isinstance(port, int):
                raise TypeError("port must be an integer")
            if not 1 <= port <= 65535:
                raise ValueError("port must be in [1, 65535]")
            parsed_port = port
        client = Client(maximum_message_size=self._maximum_message_size)
        client.connect(host, parsed_port)
        self._client = client
        self._role = SessionRole.CLIENT

    def update(self, delta_seconds: float = 0.0) -> int:
        """Process queued events without blocking a Pygame render loop."""

        if isinstance(delta_seconds, bool) or not isinstance(delta_seconds, (int, float)):
            raise TypeError("delta_seconds must be a number")
        delta = float(delta_seconds)
        if not math.isfinite(delta) or delta < 0:
            raise ValueError("delta_seconds must be finite and non-negative")
        host = self._host
        if host is not None:
            listen_events = host.poll()
            for listen_event in listen_events:
                self._handle_listen_event(listen_event)
            return len(listen_events)
        client = self._client
        if client is not None:
            client_events = client.poll()
            for client_event in client_events:
                self._handle_client_event(client_event)
            return len(client_events)
        return 0

    def send(
        self,
        name: str,
        /,
        *,
        unreliable: bool = False,
        **fields: object,
    ) -> SendStatus:
        """Send from this session's client identity to its server."""

        self._validate_message_name(name)
        self._validate_fields(name, fields)
        frame = encode_message(
            name, fields, maximum_size=self._maximum_message_size
        )
        delivery = Delivery.UNRELIABLE if unreliable else Delivery.RELIABLE
        if self._host is not None:
            return self._host.client.send(frame, delivery=delivery)
        if self._client is not None:
            return self._client.send(frame, delivery=delivery)
        raise NetworkError("session is not connected")

    def send_to(
        self,
        player: Player,
        name: str,
        /,
        *,
        unreliable: bool = False,
        **fields: object,
    ) -> SendStatus:
        """Send explicitly from a host to one connected client."""

        if self._host is None:
            raise NetworkError("send_to is available only to a host")
        connection = self._connection(player)
        self._validate_message_name(name)
        self._validate_fields(name, fields)
        frame = encode_message(name, fields, maximum_size=self._maximum_message_size)
        delivery = Delivery.UNRELIABLE if unreliable else Delivery.RELIABLE
        return self._host.authority.send(connection, frame, delivery=delivery)

    def broadcast(
        self,
        name: str,
        /,
        *,
        unreliable: bool = False,
        **fields: object,
    ) -> dict[Player, SendStatus]:
        """Send explicitly from a host to every connected client."""

        if self._host is None:
            raise NetworkError("broadcast is available only to a host")
        self._validate_message_name(name)
        self._validate_fields(name, fields)
        frame = encode_message(name, fields, maximum_size=self._maximum_message_size)
        delivery = Delivery.UNRELIABLE if unreliable else Delivery.RELIABLE
        statuses = self._host.authority.broadcast(frame, delivery=delivery)
        return {
            self._players[connection.value]: status
            for connection, status in statuses.items()
            if connection.value in self._players
        }

    def disconnect(self, player: Player, reason: str = "") -> None:
        if self._host is None:
            raise NetworkError("disconnect(player) is available only to a host")
        self._host.authority.disconnect(self._connection(player), reason)

    def close(self, reason: str = "session closed") -> None:
        """Release transport resources; repeated calls are harmless."""

        try:
            host = self._host
            client = self._client
            if host is not None:
                listen_events = host.stop(reason)
                for listen_event in listen_events:
                    self._handle_listen_event(listen_event)
            elif client is not None and client.connection is not None:
                client.disconnect(reason)
                for client_event in client.poll():
                    self._handle_client_event(client_event)
        finally:
            self._host = None
            self._client = None
            self._players.clear()
            self._role = SessionRole.CLOSED

    def _handle_listen_event(self, tagged: ListenEvent) -> None:
        event = tagged.event
        if tagged.role is ListenRole.AUTHORITY:
            if event.type is EventType.CONNECTED:
                player = Player(event.connection.value, local=tagged.local_host)
                self._players[player.id] = player
                self._emit("connect", player)
            elif event.type is EventType.DISCONNECTED:
                player = self._players.pop(
                    event.connection.value,
                    Player(event.connection.value, local=tagged.local_host),
                )
                self._emit("disconnect", player, event.reason)
            elif event.type is EventType.MESSAGE:
                player = self._players.get(
                    event.connection.value,
                    Player(event.connection.value, local=tagged.local_host),
                )
                try:
                    self._dispatch_message(player, event)
                except NetworkError:
                    host = self._host
                    if host is not None:
                        host.authority.disconnect(
                            event.connection, "malformed application message"
                        )
                    raise
        elif event.type is EventType.MESSAGE:
            try:
                self._dispatch_message(SERVER, event)
            except NetworkError:
                host = self._host
                if host is not None:
                    host.client.disconnect("malformed application message")
                raise

    def _handle_client_event(self, event: NetworkEvent) -> None:
        if event.type is EventType.CONNECTED:
            self._emit("connect", SERVER)
        elif event.type is EventType.DISCONNECTED:
            self._emit("disconnect", SERVER, event.reason)
        elif event.type is EventType.MESSAGE:
            try:
                self._dispatch_message(SERVER, event)
            except NetworkError:
                client = self._client
                if client is not None:
                    client.disconnect("malformed application message")
                raise

    def _dispatch_message(self, sender: Player, event: NetworkEvent) -> None:
        try:
            message = decode_message(
                event.payload, maximum_size=self._maximum_message_size
            )
        except ValueError as error:
            raise NetworkError(f"received malformed application message: {error}") from error
        try:
            self._validate_fields(message.name, message.fields)
        except (TypeError, ValueError) as error:
            raise NetworkError(f"received invalid application message: {error}") from error
        self._emit(message.name, sender, **message.fields)

    def _validate_fields(self, name: str, fields: dict[str, object]) -> None:
        schema = self._schemas.get(name)
        if schema is not None:
            schema.validate(fields)

    def _emit(self, name: str, *args: object, **fields: object) -> None:
        for callback in tuple(self._handlers.get(name, ())):
            callback(*args, **fields)

    def _connection(self, player: Player) -> ConnectionId:
        if not isinstance(player, Player):
            raise TypeError("player must be a rix.net.Player")
        if player.id not in self._players:
            raise ValueError("player is not connected to this session")
        return ConnectionId(player.id)

    def _require_closed(self) -> None:
        if self._role is not SessionRole.CLOSED:
            raise NetworkError("session is already open")

    @staticmethod
    def _validate_handler_name(name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("handler name must be a non-empty string")

    @staticmethod
    def _validate_message_name(name: str) -> None:
        Session._validate_handler_name(name)
        if name in {"connect", "disconnect"}:
            raise ValueError(f"{name!r} is reserved for session lifecycle callbacks")

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


__all__ = ["Player", "SERVER", "Session", "SessionRole"]
