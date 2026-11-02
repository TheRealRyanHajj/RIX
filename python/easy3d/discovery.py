"""Bounded, opt-in IPv4 LAN server discovery.

Discovery is a low-frequency UDP control plane. Gameplay traffic continues to
use :mod:`easy3d.network` and callers explicitly choose whether to connect to a
returned numeric address.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import ipaddress
import secrets
import socket
import struct
import time
import unicodedata
from typing import Final

from ._easy3d import NetworkError


DEFAULT_DISCOVERY_PORT: Final = 47777
MAX_DATAGRAM_SIZE: Final = 512
MAX_SERVER_NAME_BYTES: Final = 128

_MAGIC: Final = b"E3DD"
_WIRE_VERSION: Final = 1
_QUERY_TYPE: Final = 1
_RESPONSE_TYPE: Final = 2
_HEADER: Final = struct.Struct("<4sHBBI")
_QUERY: Final = struct.Struct("<Q")
_RESPONSE_PREFIX: Final = struct.Struct("<QQHHIH")


@dataclass(frozen=True, slots=True)
class DiscoveredServer:
    """One validated response in a browser's finite-lived cache."""

    instance_id: int
    name: str
    address: str
    port: int
    protocol_version: int
    schema_version: int
    compatible: bool
    last_seen: float


@dataclass(frozen=True, slots=True)
class DiscoveryStats:
    queries_sent: int = 0
    queries_received: int = 0
    responses_sent: int = 0
    responses_received: int = 0
    malformed_packets: int = 0
    unmatched_responses: int = 0
    rate_limited: int = 0
    cache_evictions: int = 0


class _MutableStats:
    __slots__ = tuple(DiscoveryStats.__dataclass_fields__)

    def __init__(self) -> None:
        for name in self.__slots__:
            setattr(self, name, 0)

    def snapshot(self) -> DiscoveryStats:
        return DiscoveryStats(*(getattr(self, name) for name in self.__slots__))


def _integer(name: str, value: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return value


def _finite_positive(name: str, value: float) -> float:
    result = float(value)
    if not 0.0 < result < float("inf"):
        raise ValueError(f"{name} must be finite and positive")
    return result


def _ipv4(name: str, value: str, *, allow_unspecified: bool) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a numeric IPv4 string")
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as error:
        raise ValueError(f"{name} must be a numeric IPv4 address") from error
    if address.is_unspecified and not allow_unspecified:
        raise ValueError(f"{name} cannot be the unspecified address")
    return str(address)


def _server_name(value: str) -> tuple[str, bytes]:
    if not isinstance(value, str):
        raise TypeError("name must be a string")
    if not value or any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("name must be non-empty and contain no control characters")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_SERVER_NAME_BYTES:
        raise ValueError(
            f"name must be at most {MAX_SERVER_NAME_BYTES} UTF-8 bytes"
        )
    return value, encoded


def _frame(message_type: int, payload: bytes) -> bytes:
    packet = _HEADER.pack(_MAGIC, _WIRE_VERSION, message_type, 0, len(payload)) + payload
    if len(packet) > MAX_DATAGRAM_SIZE:
        raise ValueError("discovery datagram exceeds its fixed size limit")
    return packet


def _payload(packet: bytes, expected_type: int) -> bytes:
    if len(packet) > MAX_DATAGRAM_SIZE or len(packet) < _HEADER.size:
        raise ValueError("invalid discovery datagram size")
    magic, version, message_type, flags, payload_size = _HEADER.unpack_from(packet)
    if magic != _MAGIC or version != _WIRE_VERSION:
        raise ValueError("invalid discovery envelope")
    if message_type != expected_type or flags != 0:
        raise ValueError("invalid discovery message type or flags")
    if payload_size != len(packet) - _HEADER.size:
        raise ValueError("invalid discovery payload length")
    return packet[_HEADER.size :]


def _encode_query(nonce: int) -> bytes:
    return _frame(_QUERY_TYPE, _QUERY.pack(_integer("nonce", nonce, 1, 2**64 - 1)))


def _decode_query(packet: bytes) -> int:
    payload = _payload(packet, _QUERY_TYPE)
    if len(payload) != _QUERY.size:
        raise ValueError("invalid discovery query length")
    (nonce,) = _QUERY.unpack(payload)
    if nonce == 0:
        raise ValueError("discovery nonce cannot be zero")
    return nonce


def _encode_response(
    nonce: int,
    instance_id: int,
    game_port: int,
    protocol_version: int,
    schema_version: int,
    encoded_name: bytes,
) -> bytes:
    prefix = _RESPONSE_PREFIX.pack(
        _integer("nonce", nonce, 1, 2**64 - 1),
        _integer("instance_id", instance_id, 1, 2**64 - 1),
        _integer("game_port", game_port, 1, 65535),
        _integer("protocol_version", protocol_version, 1, 65535),
        _integer("schema_version", schema_version, 1, 2**32 - 1),
        len(encoded_name),
    )
    return _frame(_RESPONSE_TYPE, prefix + encoded_name)


def _decode_response(packet: bytes) -> tuple[int, int, int, int, int, str]:
    payload = _payload(packet, _RESPONSE_TYPE)
    if len(payload) < _RESPONSE_PREFIX.size:
        raise ValueError("truncated discovery response")
    nonce, instance_id, port, protocol, schema, name_size = _RESPONSE_PREFIX.unpack_from(
        payload
    )
    if nonce == 0 or instance_id == 0 or port == 0 or protocol == 0 or schema == 0:
        raise ValueError("discovery response contains a zero required field")
    if name_size == 0 or name_size > MAX_SERVER_NAME_BYTES:
        raise ValueError("invalid discovery server name length")
    if len(payload) != _RESPONSE_PREFIX.size + name_size:
        raise ValueError("invalid discovery response length")
    try:
        name = payload[_RESPONSE_PREFIX.size :].decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("discovery server name is not valid UTF-8") from error
    _server_name(name)
    return nonce, instance_id, port, protocol, schema, name


class LanDiscoveryAnnouncer:
    """Poll-owned responder for explicitly enabled IPv4 LAN discovery."""

    __slots__ = (
        "_bind_address",
        "_discovery_port",
        "_encoded_name",
        "_game_port",
        "_instance_id",
        "_max_packets_per_poll",
        "_max_sources",
        "_minimum_response_interval",
        "_name",
        "_protocol_version",
        "_schema_version",
        "_socket",
        "_source_times",
        "_stats",
    )

    def __init__(
        self,
        name: str,
        game_port: int,
        *,
        discovery_port: int = DEFAULT_DISCOVERY_PORT,
        bind_address: str = "0.0.0.0",
        protocol_version: int = 1,
        schema_version: int = 1,
        instance_id: int | None = None,
        minimum_response_interval: float = 0.25,
        max_sources: int = 256,
        max_packets_per_poll: int = 64,
    ) -> None:
        self._name, self._encoded_name = _server_name(name)
        self._game_port = _integer("game_port", game_port, 1, 65535)
        self._discovery_port = _integer(
            "discovery_port", discovery_port, 1, 65535
        )
        self._bind_address = _ipv4(
            "bind_address", bind_address, allow_unspecified=True
        )
        self._protocol_version = _integer(
            "protocol_version", protocol_version, 1, 65535
        )
        self._schema_version = _integer(
            "schema_version", schema_version, 1, 2**32 - 1
        )
        generated_id = instance_id if instance_id is not None else secrets.randbits(64)
        if generated_id == 0:
            generated_id = 1
        self._instance_id = _integer("instance_id", generated_id, 1, 2**64 - 1)
        self._minimum_response_interval = _finite_positive(
            "minimum_response_interval", minimum_response_interval
        )
        self._max_sources = _integer("max_sources", max_sources, 1, 4096)
        self._max_packets_per_poll = _integer(
            "max_packets_per_poll", max_packets_per_poll, 1, 1024
        )
        self._socket: socket.socket | None = None
        self._source_times: OrderedDict[str, float] = OrderedDict()
        self._stats = _MutableStats()

    @property
    def is_running(self) -> bool:
        return self._socket is not None

    @property
    def name(self) -> str:
        return self._name

    @property
    def game_port(self) -> int:
        return self._game_port

    @property
    def discovery_port(self) -> int:
        return self._discovery_port

    @property
    def instance_id(self) -> int:
        return self._instance_id

    @property
    def stats(self) -> DiscoveryStats:
        return self._stats.snapshot()

    def start(self) -> None:
        if self._socket is not None:
            raise NetworkError("LAN discovery announcer is already started")
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            udp.bind((self._bind_address, self._discovery_port))
            udp.setblocking(False)
        except OSError as error:
            udp.close()
            raise NetworkError(
                f"could not bind LAN discovery UDP port {self._discovery_port}: {error}"
            ) from error
        self._socket = udp

    def poll(self, maximum_packets: int | None = None) -> int:
        udp = self._require_socket()
        limit = self._poll_limit(maximum_packets)
        responses = 0
        for _ in range(limit):
            try:
                packet, source = udp.recvfrom(MAX_DATAGRAM_SIZE + 1)
            except BlockingIOError:
                break
            except ConnectionResetError:
                self._stats.malformed_packets += 1
                continue
            except OSError as error:
                raise NetworkError(f"LAN discovery receive failed: {error}") from error
            try:
                nonce = _decode_query(packet)
            except ValueError:
                self._stats.malformed_packets += 1
                continue
            self._stats.queries_received += 1
            now = time.monotonic()
            source_address = source[0]
            previous = self._source_times.get(source_address)
            if (
                previous is not None
                and now - previous < self._minimum_response_interval
            ):
                self._stats.rate_limited += 1
                continue
            self._source_times[source_address] = now
            self._source_times.move_to_end(source_address)
            while len(self._source_times) > self._max_sources:
                self._source_times.popitem(last=False)
            response = _encode_response(
                nonce,
                self._instance_id,
                self._game_port,
                self._protocol_version,
                self._schema_version,
                self._encoded_name,
            )
            try:
                sent = udp.sendto(response, source)
            except BlockingIOError:
                continue
            except OSError as error:
                raise NetworkError(f"LAN discovery response failed: {error}") from error
            if sent == len(response):
                responses += 1
                self._stats.responses_sent += 1
        return responses

    def close(self) -> None:
        udp, self._socket = self._socket, None
        if udp is not None:
            udp.close()
        self._source_times.clear()

    def __enter__(self) -> LanDiscoveryAnnouncer:
        self.start()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise NetworkError("LAN discovery announcer is not started")
        return self._socket

    def _poll_limit(self, maximum_packets: int | None) -> int:
        if maximum_packets is None:
            return self._max_packets_per_poll
        requested = _integer("maximum_packets", maximum_packets, 1, 1024)
        return min(requested, self._max_packets_per_poll)


class LanDiscoveryBrowser:
    """Explicit query owner with a bounded, expiring result cache."""

    __slots__ = (
        "_active_nonce",
        "_bind_address",
        "_cache",
        "_cache_capacity",
        "_discovery_port",
        "_max_packets_per_poll",
        "_protocol_version",
        "_response_deadline",
        "_response_window",
        "_result_ttl",
        "_schema_version",
        "_socket",
        "_stats",
        "_target_address",
    )

    def __init__(
        self,
        *,
        discovery_port: int = DEFAULT_DISCOVERY_PORT,
        bind_address: str = "0.0.0.0",
        target_address: str = "255.255.255.255",
        protocol_version: int = 1,
        schema_version: int = 1,
        response_window: float = 1.0,
        result_ttl: float = 3.0,
        cache_capacity: int = 64,
        max_packets_per_poll: int = 64,
    ) -> None:
        self._discovery_port = _integer(
            "discovery_port", discovery_port, 1, 65535
        )
        self._bind_address = _ipv4(
            "bind_address", bind_address, allow_unspecified=True
        )
        self._target_address = _ipv4(
            "target_address", target_address, allow_unspecified=False
        )
        self._protocol_version = _integer(
            "protocol_version", protocol_version, 1, 65535
        )
        self._schema_version = _integer(
            "schema_version", schema_version, 1, 2**32 - 1
        )
        self._response_window = _finite_positive("response_window", response_window)
        self._result_ttl = _finite_positive("result_ttl", result_ttl)
        self._cache_capacity = _integer("cache_capacity", cache_capacity, 1, 4096)
        self._max_packets_per_poll = _integer(
            "max_packets_per_poll", max_packets_per_poll, 1, 1024
        )
        self._socket: socket.socket | None = None
        self._active_nonce: int | None = None
        self._response_deadline = 0.0
        self._cache: OrderedDict[tuple[int, str, int], DiscoveredServer] = (
            OrderedDict()
        )
        self._stats = _MutableStats()

    @property
    def is_running(self) -> bool:
        return self._socket is not None

    @property
    def local_port(self) -> int:
        udp = self._require_socket()
        return int(udp.getsockname()[1])

    @property
    def servers(self) -> tuple[DiscoveredServer, ...]:
        self._expire(time.monotonic())
        return tuple(self._cache.values())

    @property
    def stats(self) -> DiscoveryStats:
        return self._stats.snapshot()

    def start(self) -> None:
        if self._socket is not None:
            raise NetworkError("LAN discovery browser is already started")
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.bind((self._bind_address, 0))
            udp.setblocking(False)
        except OSError as error:
            udp.close()
            raise NetworkError(f"could not start LAN discovery: {error}") from error
        self._socket = udp

    def refresh(self, target_address: str | None = None) -> int:
        udp = self._require_socket()
        target = self._target_address
        if target_address is not None:
            target = _ipv4(
                "target_address", target_address, allow_unspecified=False
            )
        nonce = secrets.randbits(64) or 1
        query = _encode_query(nonce)
        try:
            sent = udp.sendto(query, (target, self._discovery_port))
        except OSError as error:
            raise NetworkError(f"LAN discovery query failed: {error}") from error
        if sent != len(query):
            raise NetworkError("LAN discovery query was not sent completely")
        self._active_nonce = nonce
        self._response_deadline = time.monotonic() + self._response_window
        self._stats.queries_sent += 1
        return nonce

    def poll(
        self, maximum_packets: int | None = None
    ) -> tuple[DiscoveredServer, ...]:
        udp = self._require_socket()
        if maximum_packets is None:
            limit = self._max_packets_per_poll
        else:
            requested = _integer("maximum_packets", maximum_packets, 1, 1024)
            limit = min(requested, self._max_packets_per_poll)
        discovered: list[DiscoveredServer] = []
        for _ in range(limit):
            try:
                packet, source = udp.recvfrom(MAX_DATAGRAM_SIZE + 1)
            except BlockingIOError:
                break
            except ConnectionResetError:
                self._stats.malformed_packets += 1
                continue
            except OSError as error:
                raise NetworkError(f"LAN discovery receive failed: {error}") from error
            try:
                nonce, instance, port, protocol, schema, name = _decode_response(
                    packet
                )
            except ValueError:
                self._stats.malformed_packets += 1
                continue
            now = time.monotonic()
            if (
                self._active_nonce is None
                or nonce != self._active_nonce
                or now > self._response_deadline
            ):
                self._stats.unmatched_responses += 1
                continue
            if int(source[1]) != self._discovery_port:
                self._stats.malformed_packets += 1
                continue
            address = _ipv4("response address", source[0], allow_unspecified=False)
            result = DiscoveredServer(
                instance,
                name,
                address,
                port,
                protocol,
                schema,
                protocol == self._protocol_version and schema == self._schema_version,
                now,
            )
            key = (instance, address, port)
            if key not in self._cache and len(self._cache) >= self._cache_capacity:
                self._cache.popitem(last=False)
                self._stats.cache_evictions += 1
            self._cache[key] = result
            self._cache.move_to_end(key)
            discovered.append(result)
            self._stats.responses_received += 1
        self._expire(time.monotonic())
        return tuple(discovered)

    def clear(self) -> None:
        self._cache.clear()

    def close(self) -> None:
        udp, self._socket = self._socket, None
        if udp is not None:
            udp.close()
        self._active_nonce = None
        self._response_deadline = 0.0
        self._cache.clear()

    def __enter__(self) -> LanDiscoveryBrowser:
        self.start()
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise NetworkError("LAN discovery browser is not started")
        return self._socket

    def _expire(self, now: float) -> None:
        expired = [
            key
            for key, server in self._cache.items()
            if now - server.last_seen >= self._result_ttl
        ]
        for key in expired:
            del self._cache[key]


__all__ = [
    "DEFAULT_DISCOVERY_PORT",
    "DiscoveredServer",
    "DiscoveryStats",
    "LanDiscoveryAnnouncer",
    "LanDiscoveryBrowser",
]
