"""Server-owned network object lifecycle and late-join snapshots."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import struct
import unicodedata
from weakref import WeakKeyDictionary

from ._easy3d import NetworkError
from .entity import Entity
from .math import Quat, Vec3
from .network import (
    Client,
    ConnectionId,
    Delivery,
    EventType,
    NetworkEvent,
    SendStatus,
    Server,
)
from .scene import Scene


_MAGIC = b"E3DR"
_WIRE_VERSION = 1
_BEGIN = 1
_SPAWN = 2
_DESPAWN = 3
_END = 4
_VALUE = 5
_TRANSFORM = 6
_HEADER = struct.Struct("<4sHBBI")
_BEGIN_PAYLOAD = struct.Struct("<QII16s")
_SPAWN_PAYLOAD = struct.Struct("<QI")
_DESPAWN_PAYLOAD = struct.Struct("<Q")
_END_PAYLOAD = struct.Struct("<Q")
_MAX_FRAME_SIZE = 64
_VALUE_PREFIX = struct.Struct("<QHBQI")
_MAX_VALUE_BYTES = 60 * 1024
_TRANSFORM_PAYLOAD = struct.Struct("<QQQ10f")
_MAX_TRANSFORM_SAMPLES = 256
_MAX_FLOAT32 = 3.4028234663852886e38


@dataclass(frozen=True, slots=True, order=True)
class NetworkObjectId:
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or not 1 <= self.value <= 2**64 - 1
        ):
            raise ValueError("network object ID must be a nonzero uint64")


@dataclass(frozen=True, slots=True, order=True)
class PrefabId:
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or not 1 <= self.value <= 2**32 - 1
        ):
            raise ValueError("prefab ID must be a nonzero uint32")


PrefabFactory = Callable[[Scene], Entity]


class NetworkValueType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BYTES = "bytes"


@dataclass(frozen=True, slots=True)
class NetworkVarSpec:
    id: int
    name: str
    type: NetworkValueType
    default: object
    max_bytes: int


@dataclass(frozen=True, slots=True)
class TransformSnapshot:
    """One validated authority transform sample in local entity space."""

    tick: int
    sequence: int
    position: Vec3
    rotation: Quat
    scale: Vec3


@dataclass(frozen=True, slots=True)
class NetworkTransform:
    """Schema marker for authoritative local transform replication."""

    prefab_id: PrefabId


@dataclass(frozen=True, slots=True)
class TransformReplicationStats:
    received: int
    stale_dropped: int
    unknown_dropped: int
    history_evictions: int
    interpolated: int


@dataclass(frozen=True, slots=True)
class TransformFlushStats:
    sequence: int
    tick: int
    queued: int
    filtered: int
    backpressured: int


def _encode_value(spec: NetworkVarSpec, value: object) -> bytes:
    if spec.type is NetworkValueType.BOOL:
        if not isinstance(value, bool):
            raise TypeError("bool NetworkVar requires bool")
        encoded = b"\x01" if value else b"\x00"
    elif spec.type is NetworkValueType.INT:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("int NetworkVar requires int")
        if not -(2**63) <= value <= 2**63 - 1:
            raise ValueError("int NetworkVar is outside signed int64")
        encoded = struct.pack("<q", value)
    elif spec.type is NetworkValueType.FLOAT:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("float NetworkVar requires a number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("float NetworkVar must be finite")
        encoded = struct.pack("<d", number)
    elif spec.type is NetworkValueType.STRING:
        if not isinstance(value, str):
            raise TypeError("string NetworkVar requires str")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("string NetworkVar cannot contain controls")
        encoded = value.encode("utf-8")
    else:
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError("bytes NetworkVar requires bytes-like data")
        encoded = bytes(value)
    if len(encoded) > spec.max_bytes:
        raise ValueError("NetworkVar value exceeds its declared byte bound")
    return encoded


def _decode_value(spec: NetworkVarSpec, data: bytes) -> object:
    if len(data) > spec.max_bytes:
        raise ValueError("NetworkVar payload exceeds its declared bound")
    if spec.type is NetworkValueType.BOOL:
        if data not in (b"\x00", b"\x01"):
            raise ValueError("invalid bool NetworkVar payload")
        return data == b"\x01"
    if spec.type is NetworkValueType.INT:
        if len(data) != 8:
            raise ValueError("invalid int NetworkVar payload")
        return struct.unpack("<q", data)[0]
    if spec.type is NetworkValueType.FLOAT:
        if len(data) != 8:
            raise ValueError("invalid float NetworkVar payload")
        value = struct.unpack("<d", data)[0]
        if not math.isfinite(value):
            raise ValueError("non-finite float NetworkVar payload")
        return value
    if spec.type is NetworkValueType.STRING:
        value = data.decode("utf-8", errors="strict")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("string NetworkVar payload contains controls")
        return value
    return bytes(data)


class NetworkVar:
    __slots__ = ("_authority", "_dirty", "_spec", "_value", "_version")

    def __init__(self, spec: NetworkVarSpec, *, authority: bool) -> None:
        self._spec = spec
        self._authority = authority
        self._value = spec.default
        self._version = 0
        self._dirty = False

    @property
    def value(self) -> object:
        return self._value

    @value.setter
    def value(self, value: object) -> None:
        if not self._authority:
            raise PermissionError("client NetworkVar mirrors are read-only")
        encoded = _encode_value(self._spec, value)
        normalized = _decode_value(self._spec, encoded)
        if normalized != self._value:
            if self._version == 2**64 - 1:
                raise NetworkError("NetworkVar version space is exhausted")
            self._value = normalized
            self._version += 1
            self._dirty = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def version(self) -> int:
        return self._version

    @property
    def spec(self) -> NetworkVarSpec:
        return self._spec

    def _apply(self, value: object, version: int) -> None:
        if version <= self._version:
            raise ValueError("NetworkVar version is stale or duplicated")
        self._value = value
        self._version = version


@dataclass(frozen=True, slots=True)
class PrefabRegistration:
    id: PrefabId
    name: str
    factory: PrefabFactory


class PrefabRegistry:
    """Bounded explicit prefab/schema mapping shared by authority and clients."""

    __slots__ = (
        "_capacity",
        "_entries",
        "_fields",
        "_frozen",
        "_names",
        "_schema_version",
        "_transforms",
    )

    def __init__(self, *, schema_version: int = 1, capacity: int = 1024) -> None:
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise TypeError("schema_version must be an integer")
        if not 1 <= schema_version <= 2**32 - 1:
            raise ValueError("schema_version must be a nonzero uint32")
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("capacity must be an integer")
        if not 1 <= capacity <= 4096:
            raise ValueError("capacity must be in [1, 4096]")
        self._schema_version = schema_version
        self._capacity = capacity
        self._entries: dict[PrefabId, PrefabRegistration] = {}
        self._fields: dict[PrefabId, dict[int, NetworkVarSpec]] = {}
        self._transforms: dict[PrefabId, NetworkTransform] = {}
        self._names: set[str] = set()
        self._frozen = False

    @property
    def schema_version(self) -> int:
        return self._schema_version

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    @property
    def registrations(self) -> tuple[PrefabRegistration, ...]:
        return tuple(self._entries[key] for key in sorted(self._entries))

    @property
    def fingerprint(self) -> bytes:
        digest = hashlib.blake2s(digest_size=16, person=b"E3DPref")
        digest.update(struct.pack("<I", self._schema_version))
        for registration in self.registrations:
            encoded = registration.name.encode("utf-8")
            digest.update(struct.pack("<IH", registration.id.value, len(encoded)))
            digest.update(encoded)
            for spec in self.variables(registration.id):
                default = _encode_value(spec, spec.default)
                field_name = spec.name.encode("utf-8")
                digest.update(
                    struct.pack(
                        "<HBBHH",
                        spec.id,
                        list(NetworkValueType).index(spec.type) + 1,
                        0,
                        spec.max_bytes,
                        len(field_name),
                    )
                )
                digest.update(field_name)
                digest.update(struct.pack("<I", len(default)))
                digest.update(default)
            digest.update(b"\x01" if registration.id in self._transforms else b"\x00")
        return digest.digest()

    def register(
        self,
        prefab_id: PrefabId | int,
        name: str,
        factory: PrefabFactory,
    ) -> PrefabRegistration:
        if self._frozen:
            raise RuntimeError("prefab registry is frozen")
        identifier = prefab_id if isinstance(prefab_id, PrefabId) else PrefabId(prefab_id)
        if not isinstance(name, str):
            raise TypeError("prefab name must be a string")
        encoded = name.encode("utf-8")
        if (
            not encoded
            or len(encoded) > 64
            or any(unicodedata.category(char).startswith("C") for char in name)
        ):
            raise ValueError("prefab name must be 1-64 safe UTF-8 bytes")
        if not callable(factory):
            raise TypeError("prefab factory must be callable")
        if identifier in self._entries or name in self._names:
            raise ValueError("prefab ID and name must both be unique")
        if len(self._entries) >= self._capacity:
            raise NetworkError("prefab registry capacity is exhausted")
        registration = PrefabRegistration(identifier, name, factory)
        self._entries[identifier] = registration
        self._fields[identifier] = {}
        self._names.add(name)
        return registration

    def register_variable(
        self,
        prefab_id: PrefabId | int,
        field_id: int,
        name: str,
        value_type: NetworkValueType | str,
        default: object,
        *,
        max_bytes: int = 256,
    ) -> NetworkVarSpec:
        if self._frozen:
            raise RuntimeError("prefab registry is frozen")
        registration = self.resolve(prefab_id)
        if isinstance(field_id, bool) or not isinstance(field_id, int):
            raise TypeError("field_id must be an integer")
        if not 1 <= field_id <= 65535:
            raise ValueError("field_id must be a nonzero uint16")
        if not isinstance(name, str):
            raise TypeError("field name must be a string")
        encoded_name = name.encode("utf-8")
        if (
            not encoded_name
            or len(encoded_name) > 64
            or any(unicodedata.category(char).startswith("C") for char in name)
        ):
            raise ValueError("field name must be 1-64 safe UTF-8 bytes")
        try:
            kind = value_type if isinstance(value_type, NetworkValueType) else NetworkValueType(value_type)
        except ValueError as error:
            raise ValueError("unsupported NetworkVar type") from error
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")
        if not 1 <= max_bytes <= _MAX_VALUE_BYTES:
            raise ValueError("max_bytes is outside the supported bound")
        fields = self._fields[registration.id]
        if field_id in fields or any(item.name == name for item in fields.values()):
            raise ValueError("field ID and name must both be unique per prefab")
        if len(fields) >= 256:
            raise NetworkError("prefab NetworkVar capacity is exhausted")
        spec = NetworkVarSpec(field_id, name, kind, default, max_bytes)
        normalized = _decode_value(spec, _encode_value(spec, default))
        spec = NetworkVarSpec(field_id, name, kind, normalized, max_bytes)
        fields[field_id] = spec
        return spec

    def variables(self, prefab_id: PrefabId | int) -> tuple[NetworkVarSpec, ...]:
        registration = self.resolve(prefab_id)
        return tuple(self._fields[registration.id][key] for key in sorted(self._fields[registration.id]))

    def register_transform(self, prefab_id: PrefabId | int) -> NetworkTransform:
        """Declare that a prefab receives authoritative transform snapshots."""

        if self._frozen:
            raise RuntimeError("prefab registry is frozen")
        registration = self.resolve(prefab_id)
        if registration.id in self._transforms:
            raise ValueError("prefab transform replication is already registered")
        result = NetworkTransform(registration.id)
        self._transforms[registration.id] = result
        return result

    def has_transform(self, prefab_id: PrefabId | int) -> bool:
        registration = self.resolve(prefab_id)
        return registration.id in self._transforms

    def freeze(self) -> None:
        if not self._entries:
            raise RuntimeError("cannot freeze an empty prefab registry")
        self._frozen = True

    def resolve(self, prefab_id: PrefabId | int) -> PrefabRegistration:
        identifier = prefab_id if isinstance(prefab_id, PrefabId) else PrefabId(prefab_id)
        try:
            return self._entries[identifier]
        except KeyError as error:
            raise KeyError(f"unknown prefab ID {identifier.value}") from error


@dataclass(frozen=True, slots=True)
class ReplicatedObject:
    id: NetworkObjectId
    prefab_id: PrefabId
    entity: Entity


def _frame(message_type: int, payload: bytes) -> bytes:
    result = _HEADER.pack(_MAGIC, _WIRE_VERSION, message_type, 0, len(payload)) + payload
    if len(result) > _MAX_FRAME_SIZE:
        raise RuntimeError("replication frame exceeded its fixed bound")
    return result


def _value_frame(
    object_id: NetworkObjectId,
    variable: NetworkVar,
) -> bytes:
    data = _encode_value(variable.spec, variable.value)
    type_code = list(NetworkValueType).index(variable.spec.type) + 1
    payload = _VALUE_PREFIX.pack(
        object_id.value,
        variable.spec.id,
        type_code,
        variable.version,
        len(data),
    ) + data
    return _HEADER.pack(_MAGIC, _WIRE_VERSION, _VALUE, 0, len(payload)) + payload


def _transform_frame(
    replicated: ReplicatedObject,
    sequence: int,
    tick: int,
) -> bytes:
    position = tuple(replicated.entity.position)
    rotation = tuple(replicated.entity.quaternion.normalized())
    scale = tuple(replicated.entity.scale)
    values = (*position, *rotation, *scale)
    if not all(
        math.isfinite(value) and abs(value) <= _MAX_FLOAT32 for value in values
    ):
        raise ValueError("replicated transform components must fit finite float32")
    if any(value == 0.0 for value in scale):
        raise ValueError("replicated transform scale components must be nonzero")
    payload = _TRANSFORM_PAYLOAD.pack(
        replicated.id.value,
        sequence,
        tick,
        *values,
    )
    return _HEADER.pack(_MAGIC, _WIRE_VERSION, _TRANSFORM, 0, len(payload)) + payload


def _decode(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < _HEADER.size or len(frame) > _HEADER.size + _VALUE_PREFIX.size + _MAX_VALUE_BYTES:
        raise ValueError("invalid replication frame size")
    magic, version, message_type, flags, size = _HEADER.unpack_from(frame)
    if magic != _MAGIC or version != _WIRE_VERSION or flags != 0:
        raise ValueError("invalid replication frame envelope")
    if message_type not in (_BEGIN, _SPAWN, _DESPAWN, _END, _VALUE, _TRANSFORM):
        raise ValueError("unknown replication frame type")
    if message_type not in (_VALUE, _TRANSFORM) and len(frame) > _MAX_FRAME_SIZE:
        raise ValueError("lifecycle frame exceeds its fixed bound")
    if message_type == _TRANSFORM and len(frame) != _HEADER.size + _TRANSFORM_PAYLOAD.size:
        raise ValueError("invalid transform frame size")
    if size != len(frame) - _HEADER.size:
        raise ValueError("invalid replication payload length")
    return message_type, frame[_HEADER.size :]


_attached_servers: WeakKeyDictionary[Server, bool] = WeakKeyDictionary()


class ServerReplication:
    """Server-only allocator and lifecycle broadcaster."""

    __slots__ = (
        "_closed",
        "_max_objects",
        "_max_transform_sends",
        "_next_id",
        "_objects",
        "_old_connect",
        "_old_disconnect",
        "_old_message",
        "_registry",
        "_server",
        "_snapshot_epoch",
        "_last_transform_flush",
        "_last_transform_tick",
        "_relevance_filter",
        "_transform_sequence",
        "_variables",
        "__weakref__",
    )

    def __init__(
        self,
        server: Server,
        registry: PrefabRegistry,
        *,
        max_objects: int = 65536,
        max_transform_sends: int = 65536,
        relevance_filter: Callable[[ConnectionId, ReplicatedObject], bool] | None = None,
    ) -> None:
        if not isinstance(server, Server):
            raise TypeError("server must be an easy3d.Server")
        if not isinstance(registry, PrefabRegistry):
            raise TypeError("registry must be a PrefabRegistry")
        if isinstance(max_objects, bool) or not isinstance(max_objects, int):
            raise TypeError("max_objects must be an integer")
        if not 1 <= max_objects <= 1_000_000:
            raise ValueError("max_objects must be in [1, 1000000]")
        if isinstance(max_transform_sends, bool) or not isinstance(max_transform_sends, int):
            raise TypeError("max_transform_sends must be an integer")
        if not 1 <= max_transform_sends <= 1_000_000:
            raise ValueError("max_transform_sends must be in [1, 1000000]")
        if relevance_filter is not None and not callable(relevance_filter):
            raise TypeError("relevance_filter must be callable")
        if server in _attached_servers:
            raise RuntimeError("this server already has a replication owner")
        if server.connections:
            raise RuntimeError("attach replication before clients connect")
        registry.freeze()
        self._server = server
        self._registry = registry
        self._max_objects = max_objects
        self._max_transform_sends = max_transform_sends
        self._objects: dict[NetworkObjectId, ReplicatedObject] = {}
        self._next_id = 1
        self._snapshot_epoch = 0
        self._transform_sequence = 0
        self._last_transform_tick: int | None = None
        self._relevance_filter = relevance_filter
        self._last_transform_flush = TransformFlushStats(0, 0, 0, 0, 0)
        self._variables: dict[tuple[NetworkObjectId, int], NetworkVar] = {}
        self._closed = False
        self._old_connect = server.on_connect
        self._old_disconnect = server.on_disconnect
        self._old_message = server.on_message
        server.on_connect = self._on_connect
        server.on_disconnect = self._on_disconnect
        server.on_message = self._on_message
        _attached_servers[server] = True

    @property
    def objects(self) -> tuple[ReplicatedObject, ...]:
        return tuple(self._objects[key] for key in sorted(self._objects))

    @property
    def last_transform_flush(self) -> TransformFlushStats:
        return self._last_transform_flush

    def set_relevance_filter(
        self,
        relevance_filter: Callable[[ConnectionId, ReplicatedObject], bool] | None,
    ) -> None:
        if relevance_filter is not None and not callable(relevance_filter):
            raise TypeError("relevance_filter must be callable")
        self._relevance_filter = relevance_filter

    def spawn(self, prefab_id: PrefabId | int) -> ReplicatedObject:
        if self._closed:
            raise RuntimeError("server replication is closed")
        if len(self._objects) >= self._max_objects:
            raise NetworkError("network object capacity is exhausted")
        if self._next_id > 2**64 - 1:
            raise NetworkError("network object ID space is exhausted")
        scene = self._server.scene
        if scene is None:
            raise RuntimeError("the authority must load a scene before spawning")
        registration = self._registry.resolve(prefab_id)
        entity = registration.factory(scene)
        if not isinstance(entity, Entity) or entity.scene is not scene or not entity.is_alive:
            if isinstance(entity, Entity) and entity.is_alive:
                entity.destroy()
            raise TypeError("prefab factory must return a live Entity in the supplied scene")
        identifier = NetworkObjectId(self._next_id)
        self._next_id += 1
        replicated = ReplicatedObject(identifier, registration.id, entity)
        self._objects[identifier] = replicated
        for spec in self._registry.variables(registration.id):
            self._variables[(identifier, spec.id)] = NetworkVar(spec, authority=True)
        self._broadcast(
            _frame(
                _SPAWN,
                _SPAWN_PAYLOAD.pack(identifier.value, registration.id.value),
            )
        )
        return replicated

    def despawn(self, object_id: NetworkObjectId | int) -> Entity:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            replicated = self._objects.pop(identifier)
        except KeyError as error:
            raise KeyError(f"unknown network object ID {identifier.value}") from error
        self._broadcast(_frame(_DESPAWN, _DESPAWN_PAYLOAD.pack(identifier.value)))
        for key in [key for key in self._variables if key[0] == identifier]:
            del self._variables[key]
        if replicated.entity.is_alive:
            replicated.entity.destroy()
        return replicated.entity

    def variable(
        self, object_id: NetworkObjectId | int, field_id: int
    ) -> NetworkVar:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            return self._variables[(identifier, field_id)]
        except KeyError as error:
            raise KeyError("unknown network object field") from error

    def flush(self) -> int:
        count = 0
        for (identifier, _field), variable in sorted(
            self._variables.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            if variable.dirty:
                self._broadcast(_value_frame(identifier, variable))
                variable._dirty = False
                count += 1
        return count

    def flush_transforms(self, tick: int) -> TransformFlushStats:
        """Queue one replaceable transform snapshot for each relevant replica."""

        if self._closed:
            raise RuntimeError("server replication is closed")
        if isinstance(tick, bool) or not isinstance(tick, int):
            raise TypeError("tick must be an integer")
        if not 0 <= tick <= 2**64 - 1:
            raise ValueError("tick must be a uint64")
        if self._last_transform_tick is not None and tick < self._last_transform_tick:
            raise ValueError("transform snapshot ticks cannot decrease")
        if self._transform_sequence == 2**64 - 1:
            raise NetworkError("transform snapshot sequence space is exhausted")
        transform_objects = tuple(
            item for item in self.objects if self._registry.has_transform(item.prefab_id)
        )
        connections = self._server.connections
        if len(transform_objects) * len(connections) > self._max_transform_sends:
            raise NetworkError("transform snapshot send bound is exceeded")
        sequence = self._transform_sequence + 1
        sends: list[tuple[ConnectionId, bytes]] = []
        filtered = 0
        frames = {
            item.id: _transform_frame(item, sequence, tick)
            for item in transform_objects
        }
        for connection in connections:
            for item in transform_objects:
                if self._relevance_filter is not None and not self._relevance_filter(
                    connection, item
                ):
                    filtered += 1
                    continue
                sends.append((connection, frames[item.id]))
        queued = 0
        backpressured = 0
        for connection, frame in sends:
            status = self._server.send(
                connection, frame, delivery=Delivery.UNRELIABLE
            )
            if status is SendStatus.QUEUED:
                queued += 1
            else:
                backpressured += 1
        self._transform_sequence = sequence
        self._last_transform_tick = tick
        self._last_transform_flush = TransformFlushStats(
            sequence, tick, queued, filtered, backpressured
        )
        return self._last_transform_flush

    def close(self, *, destroy: bool = False) -> None:
        if self._closed:
            return
        if self._server.on_connect == self._on_connect:
            self._server.on_connect = self._old_connect
        if self._server.on_disconnect == self._on_disconnect:
            self._server.on_disconnect = self._old_disconnect
        if self._server.on_message == self._on_message:
            self._server.on_message = self._old_message
        _attached_servers.pop(self._server, None)
        if destroy:
            for replicated in self.objects:
                if replicated.entity.is_alive:
                    replicated.entity.destroy()
            self._objects.clear()
            self._variables.clear()
        self._closed = True

    def _on_connect(self, server: Server, connection: ConnectionId) -> None:
        self._send_snapshot(connection)
        if self._old_connect is not None:
            self._old_connect(server, connection)

    def _on_disconnect(self, server: Server, event: NetworkEvent) -> None:
        if self._old_disconnect is not None:
            self._old_disconnect(server, event)

    def _on_message(self, server: Server, event: NetworkEvent) -> None:
        if event.payload.startswith(_MAGIC):
            server.disconnect(event.connection, "client-authored replication is forbidden")
            return
        if self._old_message is not None:
            self._old_message(server, event)

    def _send_snapshot(self, connection: ConnectionId) -> None:
        if self._snapshot_epoch == 2**64 - 1:
            self._server.disconnect(connection, "replication snapshot epoch exhausted")
            return
        self._snapshot_epoch += 1
        epoch = self._snapshot_epoch
        begin = _frame(
            _BEGIN,
            _BEGIN_PAYLOAD.pack(
                epoch,
                len(self._objects),
                self._registry.schema_version,
                self._registry.fingerprint,
            ),
        )
        if self._server.send(connection, begin) is not SendStatus.QUEUED:
            self._server.disconnect(connection, "replication snapshot backpressure")
            return
        for item in self.objects:
            spawn = _frame(
                _SPAWN,
                _SPAWN_PAYLOAD.pack(item.id.value, item.prefab_id.value),
            )
            if self._server.send(connection, spawn) is not SendStatus.QUEUED:
                self._server.disconnect(connection, "replication snapshot backpressure")
                return
            for spec in self._registry.variables(item.prefab_id):
                value = _value_frame(item.id, self._variables[(item.id, spec.id)])
                if self._server.send(connection, value) is not SendStatus.QUEUED:
                    self._server.disconnect(
                        connection, "replication snapshot backpressure"
                    )
                    return
            if self._registry.has_transform(item.prefab_id):
                try:
                    relevant = (
                        self._relevance_filter is None
                        or self._relevance_filter(connection, item)
                    )
                except Exception:
                    self._server.disconnect(connection, "replication relevance callback failed")
                    return
                if relevant:
                    transform = _transform_frame(
                        item,
                        self._transform_sequence,
                        0 if self._last_transform_tick is None else self._last_transform_tick,
                    )
                    if self._server.send(connection, transform) is not SendStatus.QUEUED:
                        self._server.disconnect(
                            connection, "replication snapshot backpressure"
                        )
                        return
        end = _frame(_END, _END_PAYLOAD.pack(epoch))
        if self._server.send(connection, end) is not SendStatus.QUEUED:
            self._server.disconnect(connection, "replication snapshot backpressure")

    def _broadcast(self, frame: bytes) -> None:
        for connection, status in self._server.broadcast(frame).items():
            if status is not SendStatus.QUEUED:
                self._server.disconnect(connection, "replication update backpressure")


def _lerp_vec3(first: Vec3, second: Vec3, amount: float) -> Vec3:
    return Vec3(
        first.x + (second.x - first.x) * amount,
        first.y + (second.y - first.y) * amount,
        first.z + (second.z - first.z) * amount,
    )


def _lerp_scale(first: Vec3, second: Vec3, amount: float) -> Vec3:
    def component(left: float, right: float) -> float:
        if left * right < 0.0:
            return left if amount < 0.5 else right
        return left + (right - left) * amount

    return Vec3(
        component(first.x, second.x),
        component(first.y, second.y),
        component(first.z, second.z),
    )


def _nlerp_quat(first: Quat, second: Quat, amount: float) -> Quat:
    left = tuple(first.normalized())
    right = tuple(second.normalized())
    if sum(a * b for a, b in zip(left, right, strict=True)) < 0.0:
        right = tuple(-value for value in right)
    return Quat(
        tuple(a + (b - a) * amount for a, b in zip(left, right, strict=True))
    ).normalized()


def _interpolated_snapshot(
    history: deque[TransformSnapshot], render_tick: float
) -> TransformSnapshot:
    if render_tick <= history[0].tick:
        return history[0]
    if render_tick >= history[-1].tick:
        return history[-1]
    for first, second in zip(history, tuple(history)[1:]):
        if first.tick <= render_tick <= second.tick:
            amount = (render_tick - first.tick) / (second.tick - first.tick)
            return TransformSnapshot(
                int(render_tick),
                second.sequence,
                _lerp_vec3(first.position, second.position, amount),
                _nlerp_quat(first.rotation, second.rotation, amount),
                _lerp_scale(first.scale, second.scale, amount),
            )
    return history[-1]


class ClientReplication:
    """Apply validated authority lifecycle frames to one client scene."""

    __slots__ = (
        "_client",
        "_expected_count",
        "_history_evictions",
        "_interpolated",
        "_max_objects",
        "_max_transform_samples",
        "_objects",
        "_received_count",
        "_received_transforms",
        "_registry",
        "_scene",
        "_snapshot_epoch",
        "_snapshot_fields",
        "_stale_transforms",
        "_synchronized",
        "_transform_history",
        "_unknown_transforms",
        "_variables",
    )

    def __init__(
        self,
        client: Client,
        scene: Scene,
        registry: PrefabRegistry,
        *,
        max_objects: int = 65536,
        max_transform_samples: int = 32,
    ) -> None:
        if not isinstance(client, Client):
            raise TypeError("client must be an easy3d.network.Client")
        if not isinstance(scene, Scene):
            raise TypeError("scene must be an easy3d.Scene")
        if not isinstance(registry, PrefabRegistry):
            raise TypeError("registry must be a PrefabRegistry")
        if isinstance(max_objects, bool) or not isinstance(max_objects, int):
            raise TypeError("max_objects must be an integer")
        if not 1 <= max_objects <= 1_000_000:
            raise ValueError("max_objects must be in [1, 1000000]")
        if isinstance(max_transform_samples, bool) or not isinstance(
            max_transform_samples, int
        ):
            raise TypeError("max_transform_samples must be an integer")
        if not 2 <= max_transform_samples <= _MAX_TRANSFORM_SAMPLES:
            raise ValueError("max_transform_samples must be in [2, 256]")
        registry.freeze()
        self._client = client
        self._scene = scene
        self._registry = registry
        self._max_objects = max_objects
        self._max_transform_samples = max_transform_samples
        self._objects: dict[NetworkObjectId, ReplicatedObject] = {}
        self._snapshot_epoch: int | None = None
        self._snapshot_fields: set[tuple[NetworkObjectId, int]] = set()
        self._expected_count = 0
        self._received_count = 0
        self._synchronized = False
        self._variables: dict[tuple[NetworkObjectId, int], NetworkVar] = {}
        self._transform_history: dict[
            NetworkObjectId, deque[TransformSnapshot]
        ] = {}
        self._received_transforms = 0
        self._stale_transforms = 0
        self._unknown_transforms = 0
        self._history_evictions = 0
        self._interpolated = 0

    @property
    def objects(self) -> tuple[ReplicatedObject, ...]:
        return tuple(self._objects[key] for key in sorted(self._objects))

    @property
    def is_synchronized(self) -> bool:
        return self._synchronized

    @property
    def transform_stats(self) -> TransformReplicationStats:
        return TransformReplicationStats(
            self._received_transforms,
            self._stale_transforms,
            self._unknown_transforms,
            self._history_evictions,
            self._interpolated,
        )

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        application: list[NetworkEvent] = []
        for event in self._client.poll(maximum_events):
            if event.type is EventType.DISCONNECTED:
                self.clear()
                application.append(event)
            elif event.type is EventType.MESSAGE and event.payload.startswith(_MAGIC):
                try:
                    self._apply(event.payload)
                except (KeyError, TypeError, ValueError, RuntimeError) as error:
                    if self._client.connection is not None:
                        self._client.disconnect("invalid replication lifecycle frame")
                    self.clear()
                    raise NetworkError(f"invalid replication lifecycle frame: {error}") from error
            else:
                application.append(event)
        return tuple(application)

    def variable(
        self, object_id: NetworkObjectId | int, field_id: int
    ) -> NetworkVar:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            return self._variables[(identifier, field_id)]
        except KeyError as error:
            raise KeyError("unknown network object field") from error

    def transform_snapshots(
        self, object_id: NetworkObjectId | int
    ) -> tuple[TransformSnapshot, ...]:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        if identifier not in self._objects:
            raise KeyError(f"unknown network object ID {identifier.value}")
        return tuple(self._transform_history.get(identifier, ()))

    def interpolate_transforms(self, render_tick: float) -> int:
        """Apply clamped interpolation at ``render_tick`` to client replicas."""

        if isinstance(render_tick, bool) or not isinstance(render_tick, (int, float)):
            raise TypeError("render_tick must be a number")
        value = float(render_tick)
        if not math.isfinite(value) or value < 0 or value > 2**64 - 1:
            raise ValueError("render_tick must be a finite non-negative uint64 range value")
        if not self._synchronized:
            raise RuntimeError("cannot interpolate before the initial snapshot completes")
        applied = 0
        for identifier in sorted(self._transform_history):
            history = self._transform_history[identifier]
            if not history:
                continue
            sample = _interpolated_snapshot(history, value)
            replicated = self._objects.get(identifier)
            if replicated is None or not replicated.entity.is_alive:
                continue
            replicated.entity.position = sample.position
            replicated.entity.quaternion = sample.rotation
            replicated.entity.scale = sample.scale
            applied += 1
        self._interpolated += applied
        return applied

    def clear(self) -> None:
        for replicated in self.objects:
            if replicated.entity.is_alive:
                replicated.entity.destroy()
        self._objects.clear()
        self._variables.clear()
        self._transform_history.clear()
        self._snapshot_epoch = None
        self._snapshot_fields.clear()
        self._expected_count = 0
        self._received_count = 0
        self._synchronized = False

    def _apply(self, frame: bytes) -> None:
        message_type, payload = _decode(frame)
        if message_type == _BEGIN:
            if len(payload) != _BEGIN_PAYLOAD.size:
                raise ValueError("invalid snapshot-begin size")
            epoch, count, schema, fingerprint = _BEGIN_PAYLOAD.unpack(payload)
            if epoch == 0 or count > self._max_objects:
                raise ValueError("invalid snapshot bounds")
            if schema != self._registry.schema_version or fingerprint != self._registry.fingerprint:
                raise ValueError("prefab registry schema/fingerprint mismatch")
            self.clear()
            self._snapshot_epoch = epoch
            self._expected_count = count
            return
        if message_type == _SPAWN:
            if len(payload) != _SPAWN_PAYLOAD.size:
                raise ValueError("invalid spawn size")
            if self._snapshot_epoch is None and not self._synchronized:
                raise RuntimeError("spawn arrived before snapshot begin")
            object_value, prefab_value = _SPAWN_PAYLOAD.unpack(payload)
            identifier = NetworkObjectId(object_value)
            if identifier in self._objects or len(self._objects) >= self._max_objects:
                raise ValueError("duplicate or excessive network object")
            registration = self._registry.resolve(prefab_value)
            entity = registration.factory(self._scene)
            if (
                not isinstance(entity, Entity)
                or entity.scene is not self._scene
                or not entity.is_alive
            ):
                if isinstance(entity, Entity) and entity.is_alive:
                    entity.destroy()
                raise TypeError("prefab factory returned an invalid client entity")
            self._objects[identifier] = ReplicatedObject(identifier, registration.id, entity)
            for spec in self._registry.variables(registration.id):
                self._variables[(identifier, spec.id)] = NetworkVar(
                    spec, authority=False
                )
            if self._snapshot_epoch is not None:
                self._received_count += 1
                if self._received_count > self._expected_count:
                    raise ValueError("snapshot contains too many objects")
            return
        if message_type == _DESPAWN:
            if len(payload) != _DESPAWN_PAYLOAD.size or not self._synchronized:
                raise ValueError("invalid despawn state or size")
            (object_value,) = _DESPAWN_PAYLOAD.unpack(payload)
            identifier = NetworkObjectId(object_value)
            try:
                replicated = self._objects.pop(identifier)
            except KeyError as error:
                raise ValueError("despawn references an unknown object") from error
            if replicated.entity.is_alive:
                replicated.entity.destroy()
            for key in [key for key in self._variables if key[0] == identifier]:
                del self._variables[key]
            self._transform_history.pop(identifier, None)
            return
        if message_type == _VALUE:
            if len(payload) < _VALUE_PREFIX.size:
                raise ValueError("invalid NetworkVar update size")
            object_value, field_id, type_code, version, size = (
                _VALUE_PREFIX.unpack_from(payload)
            )
            if size != len(payload) - _VALUE_PREFIX.size:
                raise ValueError("invalid NetworkVar payload length")
            identifier = NetworkObjectId(object_value)
            try:
                variable = self._variables[(identifier, field_id)]
                declared = list(NetworkValueType).index(variable.spec.type) + 1
            except (KeyError, ValueError) as error:
                raise ValueError("unknown NetworkVar object, field or type") from error
            if type_code != declared:
                raise ValueError("NetworkVar wire type does not match schema")
            value = _decode_value(variable.spec, payload[_VALUE_PREFIX.size :])
            field_key = (identifier, field_id)
            if self._snapshot_epoch is not None:
                if field_key in self._snapshot_fields or version < variable.version:
                    raise ValueError("snapshot NetworkVar is duplicated or stale")
                if version == variable.version:
                    variable._value = value
                else:
                    variable._apply(value, version)
                self._snapshot_fields.add(field_key)
            else:
                variable._apply(value, version)
            return
        if message_type == _TRANSFORM:
            if len(payload) != _TRANSFORM_PAYLOAD.size:
                raise ValueError("invalid transform update size")
            unpacked = _TRANSFORM_PAYLOAD.unpack(payload)
            object_value, sequence, tick = unpacked[:3]
            identifier = NetworkObjectId(object_value)
            values = unpacked[3:]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("transform update contains non-finite components")
            replicated = self._objects.get(identifier)
            self._received_transforms += 1
            if replicated is None:
                self._unknown_transforms += 1
                return
            if not self._registry.has_transform(replicated.prefab_id):
                raise ValueError("transform update is not declared by the prefab schema")
            position = Vec3(values[:3])
            try:
                rotation = Quat(values[3:7]).normalized()
            except ValueError as error:
                raise ValueError("transform update contains a zero quaternion") from error
            scale = Vec3(values[7:10])
            if any(component == 0.0 for component in scale):
                raise ValueError("transform update contains a zero scale component")
            history = self._transform_history.setdefault(
                identifier, deque(maxlen=self._max_transform_samples)
            )
            if history and (
                sequence <= history[-1].sequence or tick < history[-1].tick
            ):
                self._stale_transforms += 1
                return
            snapshot = TransformSnapshot(tick, sequence, position, rotation, scale)
            if history and tick == history[-1].tick:
                history[-1] = snapshot
                return
            if len(history) == self._max_transform_samples:
                self._history_evictions += 1
            history.append(snapshot)
            return
        if len(payload) != _END_PAYLOAD.size or self._snapshot_epoch is None:
            raise ValueError("invalid snapshot-end state or size")
        (epoch,) = _END_PAYLOAD.unpack(payload)
        expected_fields = sum(
            len(self._registry.variables(item.prefab_id)) for item in self.objects
        )
        if (
            epoch != self._snapshot_epoch
            or self._received_count != self._expected_count
            or len(self._snapshot_fields) != expected_fields
        ):
            raise ValueError("snapshot end does not match its declaration")
        self._snapshot_epoch = None
        self._snapshot_fields.clear()
        self._synchronized = True


__all__ = [
    "ClientReplication",
    "NetworkObjectId",
    "NetworkTransform",
    "NetworkValueType",
    "NetworkVar",
    "NetworkVarSpec",
    "PrefabId",
    "PrefabRegistration",
    "PrefabRegistry",
    "ReplicatedObject",
    "ServerReplication",
    "TransformFlushStats",
    "TransformReplicationStats",
    "TransformSnapshot",
]
