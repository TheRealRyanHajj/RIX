"""Server-owned network object lifecycle and late-join snapshots."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import struct
import time
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
_WIRE_VERSION = 2
_BEGIN = 1
_SPAWN = 2
_DESPAWN = 3
_END = 4
_VALUE = 5
_TRANSFORM = 6
_RPC = 7
_RESYNC = 8
_TRANSFORM_ACK = 9
_TRANSFORM_DELTA = 10
_BASELINE_REQUEST = 11
_TRANSFORM_ACK_BATCH = 12
_HEADER = struct.Struct("<4sHBBI")
_BEGIN_PAYLOAD = struct.Struct("<QII16s")
_SPAWN_PAYLOAD = struct.Struct("<QI")
_DESPAWN_PAYLOAD = struct.Struct("<Q")
_END_PAYLOAD = struct.Struct("<Q")
_MAX_FRAME_SIZE = 64
_VALUE_PREFIX = struct.Struct("<QHBQI")
_MAX_VALUE_BYTES = 60 * 1024
_TRANSFORM_PAYLOAD = struct.Struct("<QQQ10f")
_TRANSFORM_DELTA_PAYLOAD = struct.Struct("<QQQQ10h")
_TRANSFORM_ACK_PAYLOAD = struct.Struct("<QQ")
_TRANSFORM_ACK_BATCH_PREFIX = struct.Struct("<H")
_MAX_TRANSFORM_ACK_BATCH = 256
_BASELINE_REQUEST_PAYLOAD = struct.Struct("<QQ")
_MAX_TRANSFORM_SAMPLES = 256
_MAX_FLOAT32 = 3.4028234663852886e38
_RPC_PREFIX = struct.Struct("<QHQB")
_RPC_ARGUMENT_PREFIX = struct.Struct("<BI")
_MAX_RPC_ARGUMENTS = 16
_MAX_RPC_BYTES = 60 * 1024
_RESYNC_PAYLOAD = struct.Struct("<Q")


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


class RpcDirection(str, Enum):
    CLIENT_TO_SERVER = "client_to_server"
    SERVER_TO_CLIENT = "server_to_client"


@dataclass(frozen=True, slots=True)
class NetworkVarSpec:
    id: int
    name: str
    type: NetworkValueType
    default: object
    max_bytes: int


@dataclass(frozen=True, slots=True)
class RpcArgumentSpec:
    type: NetworkValueType
    max_bytes: int


@dataclass(frozen=True, slots=True)
class RpcSpec:
    id: int
    name: str
    direction: RpcDirection
    arguments: tuple[RpcArgumentSpec, ...]
    delivery: Delivery
    rate_limit: int
    require_owner: bool
    handler: Callable[..., None]


@dataclass(frozen=True, slots=True)
class RpcStats:
    received: int
    executed: int
    rate_limited: int


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
class DeltaBaselineStats:
    full_received: int
    delta_received: int
    acknowledgements_sent: int
    recovery_requests: int


@dataclass(frozen=True, slots=True)
class TransformFlushStats:
    sequence: int
    tick: int
    queued: int
    filtered: int
    backpressured: int
    budget_deferred: int = 0
    full_snapshots: int = 0
    delta_snapshots: int = 0
    bytes_queued: int = 0


class SpatialInterest:
    """Bounded distance interest and distance-derived priority per connection."""

    __slots__ = ("_radius", "_radius_squared", "_observers")

    def __init__(self, radius: float) -> None:
        if isinstance(radius, bool) or not isinstance(radius, (int, float)):
            raise TypeError("spatial interest radius must be a number")
        value = float(radius)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("spatial interest radius must be finite and positive")
        self._radius = value
        self._radius_squared = value * value
        self._observers: dict[ConnectionId, Vec3] = {}

    @property
    def radius(self) -> float:
        return self._radius

    def set_observer(
        self, connection: ConnectionId, position: Vec3 | tuple[float, float, float]
    ) -> None:
        if not isinstance(connection, ConnectionId):
            raise TypeError("connection must be an easy3d.network.ConnectionId")
        self._observers[connection] = Vec3.from_value(position)

    def remove_observer(self, connection: ConnectionId) -> None:
        self._observers.pop(connection, None)

    def relevant(self, connection: ConnectionId, item: ReplicatedObject) -> bool:
        observer = self._observers.get(connection)
        if observer is None:
            return False
        offset = item.entity.position - observer
        return offset.length_squared <= self._radius_squared

    def priority(self, connection: ConnectionId, item: ReplicatedObject) -> float:
        observer = self._observers.get(connection)
        if observer is None:
            return float("-inf")
        distance = (item.entity.position - observer).length
        return max(0.0, self._radius - distance)


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
        "_rpcs",
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
        self._rpcs: dict[PrefabId, dict[int, RpcSpec]] = {}
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
            for spec in self.rpcs(registration.id):
                rpc_name = spec.name.encode("utf-8")
                digest.update(
                    struct.pack(
                        "<HBBBBH",
                        spec.id,
                        list(RpcDirection).index(spec.direction) + 1,
                        1 if spec.delivery is Delivery.RELIABLE else 2,
                        1 if spec.require_owner else 0,
                        len(spec.arguments),
                        spec.rate_limit,
                    )
                )
                digest.update(struct.pack("<H", len(rpc_name)))
                digest.update(rpc_name)
                for argument in spec.arguments:
                    digest.update(
                        struct.pack(
                            "<BH",
                            list(NetworkValueType).index(argument.type) + 1,
                            argument.max_bytes,
                        )
                    )
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
        self._rpcs[identifier] = {}
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

    def register_rpc(
        self,
        prefab_id: PrefabId | int,
        rpc_id: int,
        name: str,
        direction: RpcDirection | str,
        arguments: tuple[tuple[NetworkValueType | str, int], ...],
        handler: Callable[..., None],
        *,
        reliable: bool = True,
        rate_limit: int = 10,
        require_owner: bool = False,
    ) -> RpcSpec:
        if self._frozen:
            raise RuntimeError("prefab registry is frozen")
        registration = self.resolve(prefab_id)
        if isinstance(rpc_id, bool) or not isinstance(rpc_id, int):
            raise TypeError("rpc_id must be an integer")
        if not 1 <= rpc_id <= 65535:
            raise ValueError("rpc_id must be a nonzero uint16")
        if not isinstance(name, str):
            raise TypeError("RPC name must be a string")
        encoded_name = name.encode("utf-8")
        if (
            not encoded_name
            or len(encoded_name) > 64
            or any(unicodedata.category(char).startswith("C") for char in name)
        ):
            raise ValueError("RPC name must be 1-64 safe UTF-8 bytes")
        try:
            rpc_direction = (
                direction if isinstance(direction, RpcDirection) else RpcDirection(direction)
            )
        except ValueError as error:
            raise ValueError("unsupported RPC direction") from error
        if not isinstance(arguments, tuple) or len(arguments) > _MAX_RPC_ARGUMENTS:
            raise ValueError("RPC arguments must be a tuple with at most 16 entries")
        argument_specs: list[RpcArgumentSpec] = []
        for declaration in arguments:
            if not isinstance(declaration, tuple) or len(declaration) != 2:
                raise TypeError("each RPC argument must be a (type, max_bytes) tuple")
            value_type, max_bytes = declaration
            try:
                kind = (
                    value_type
                    if isinstance(value_type, NetworkValueType)
                    else NetworkValueType(value_type)
                )
            except ValueError as error:
                raise ValueError("unsupported RPC argument type") from error
            if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
                raise TypeError("RPC argument max_bytes must be an integer")
            if not 1 <= max_bytes <= _MAX_RPC_BYTES:
                raise ValueError("RPC argument max_bytes is outside the supported bound")
            argument_specs.append(RpcArgumentSpec(kind, max_bytes))
        if not callable(handler):
            raise TypeError("RPC handler must be callable")
        if not isinstance(reliable, bool) or not isinstance(require_owner, bool):
            raise TypeError("reliable and require_owner must be bool")
        if isinstance(rate_limit, bool) or not isinstance(rate_limit, int):
            raise TypeError("rate_limit must be an integer")
        if not 1 <= rate_limit <= 1000:
            raise ValueError("rate_limit must be in [1, 1000]")
        if rpc_direction is RpcDirection.SERVER_TO_CLIENT and require_owner:
            raise ValueError("server-to-client RPCs cannot require client ownership")
        entries = self._rpcs[registration.id]
        if rpc_id in entries or any(item.name == name for item in entries.values()):
            raise ValueError("RPC ID and name must both be unique per prefab")
        if len(entries) >= 256:
            raise NetworkError("prefab RPC capacity is exhausted")
        spec = RpcSpec(
            rpc_id,
            name,
            rpc_direction,
            tuple(argument_specs),
            Delivery.RELIABLE if reliable else Delivery.UNRELIABLE,
            rate_limit,
            require_owner,
            handler,
        )
        entries[rpc_id] = spec
        return spec

    def rpcs(self, prefab_id: PrefabId | int) -> tuple[RpcSpec, ...]:
        registration = self.resolve(prefab_id)
        return tuple(
            self._rpcs[registration.id][key]
            for key in sorted(self._rpcs[registration.id])
        )

    def rpc(self, prefab_id: PrefabId | int, rpc_id: int) -> RpcSpec:
        registration = self.resolve(prefab_id)
        try:
            return self._rpcs[registration.id][rpc_id]
        except KeyError as error:
            raise KeyError("unknown prefab RPC") from error

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


def _snapshot_from_frame(frame: bytes) -> TransformSnapshot:
    unpacked = _TRANSFORM_PAYLOAD.unpack(frame[_HEADER.size :])
    _object_value, sequence, tick = unpacked[:3]
    values = unpacked[3:]
    return TransformSnapshot(
        tick,
        sequence,
        Vec3(values[:3]),
        Quat(values[3:7]).normalized(),
        Vec3(values[7:10]),
    )


def _transform_delta_frame(
    object_id: NetworkObjectId,
    current: TransformSnapshot,
    baseline: TransformSnapshot,
) -> tuple[bytes, TransformSnapshot] | None:
    current_rotation = tuple(current.rotation)
    baseline_rotation = tuple(baseline.rotation)
    if sum(
        left * right
        for left, right in zip(current_rotation, baseline_rotation, strict=True)
    ) < 0.0:
        current_rotation = tuple(-value for value in current_rotation)
    current_position = tuple(current.position)
    baseline_position = tuple(baseline.position)
    current_scale = tuple(current.scale)
    baseline_scale = tuple(baseline.scale)
    differences = (
        *((current_position[index] - baseline_position[index]) * 100.0 for index in range(3)),
        *((current_rotation[index] - baseline_rotation[index]) * 16000.0 for index in range(4)),
        *((current_scale[index] - baseline_scale[index]) * 1000.0 for index in range(3)),
    )
    quantized = tuple(round(value) for value in differences)
    if any(value < -32767 or value > 32767 for value in quantized):
        return None
    payload = _TRANSFORM_DELTA_PAYLOAD.pack(
        object_id.value,
        current.sequence,
        current.tick,
        baseline.sequence,
        *quantized,
    )
    frame = _HEADER.pack(
        _MAGIC, _WIRE_VERSION, _TRANSFORM_DELTA, 0, len(payload)
    ) + payload
    reconstructed_position = Vec3(
        tuple(
            baseline_position[index] + quantized[index] / 100.0
            for index in range(3)
        )
    )
    reconstructed_rotation = Quat(
        tuple(
            baseline_rotation[index] + quantized[index + 3] / 16000.0
            for index in range(4)
        )
    ).normalized()
    reconstructed_scale = Vec3(
        tuple(
            baseline_scale[index] + quantized[index + 7] / 1000.0
            for index in range(3)
        )
    )
    if any(component == 0.0 for component in reconstructed_scale):
        return None
    return frame, TransformSnapshot(
        current.tick,
        current.sequence,
        reconstructed_position,
        reconstructed_rotation,
        reconstructed_scale,
    )


def _transform_ack_frame(object_id: NetworkObjectId, sequence: int) -> bytes:
    return _frame(_TRANSFORM_ACK, _TRANSFORM_ACK_PAYLOAD.pack(object_id.value, sequence))


def _transform_ack_batch_frame(
    acknowledgements: tuple[tuple[NetworkObjectId, int], ...],
) -> bytes:
    if not 1 <= len(acknowledgements) <= _MAX_TRANSFORM_ACK_BATCH:
        raise ValueError("transform ACK batch count is out of bounds")
    payload = _TRANSFORM_ACK_BATCH_PREFIX.pack(len(acknowledgements)) + b"".join(
        _TRANSFORM_ACK_PAYLOAD.pack(identifier.value, sequence)
        for identifier, sequence in acknowledgements
    )
    return _HEADER.pack(
        _MAGIC, _WIRE_VERSION, _TRANSFORM_ACK_BATCH, 0, len(payload)
    ) + payload


def _baseline_request_frame(sequence: int, object_id: NetworkObjectId) -> bytes:
    return _frame(
        _BASELINE_REQUEST,
        _BASELINE_REQUEST_PAYLOAD.pack(sequence, object_id.value),
    )


def _rpc_value_spec(index: int, argument: RpcArgumentSpec) -> NetworkVarSpec:
    return NetworkVarSpec(index + 1, f"arg{index}", argument.type, b"", argument.max_bytes)


def _resync_frame(sequence: int) -> bytes:
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise TypeError("resync sequence must be an integer")
    if not 1 <= sequence <= 2**64 - 1:
        raise ValueError("resync sequence must be a nonzero uint64")
    return _frame(_RESYNC, _RESYNC_PAYLOAD.pack(sequence))


def _rpc_frame(
    object_id: NetworkObjectId,
    spec: RpcSpec,
    sequence: int,
    arguments: tuple[object, ...],
) -> bytes:
    if len(arguments) != len(spec.arguments):
        raise TypeError("RPC argument count does not match its schema")
    payload = bytearray(
        _RPC_PREFIX.pack(object_id.value, spec.id, sequence, len(arguments))
    )
    for index, (argument_spec, value) in enumerate(
        zip(spec.arguments, arguments, strict=True)
    ):
        data = _encode_value(_rpc_value_spec(index, argument_spec), value)
        type_code = list(NetworkValueType).index(argument_spec.type) + 1
        payload.extend(_RPC_ARGUMENT_PREFIX.pack(type_code, len(data)))
        payload.extend(data)
        if len(payload) > _MAX_RPC_BYTES:
            raise ValueError("RPC frame exceeds its total byte bound")
    return _HEADER.pack(_MAGIC, _WIRE_VERSION, _RPC, 0, len(payload)) + payload


def _decode_rpc_payload(spec: RpcSpec, payload: bytes) -> tuple[int, tuple[object, ...]]:
    if len(payload) < _RPC_PREFIX.size:
        raise ValueError("invalid RPC payload size")
    _object_id, rpc_id, sequence, count = _RPC_PREFIX.unpack_from(payload)
    if rpc_id != spec.id or sequence == 0 or count != len(spec.arguments):
        raise ValueError("RPC prefix does not match its schema")
    offset = _RPC_PREFIX.size
    values: list[object] = []
    for index, argument in enumerate(spec.arguments):
        if offset + _RPC_ARGUMENT_PREFIX.size > len(payload):
            raise ValueError("truncated RPC argument prefix")
        type_code, size = _RPC_ARGUMENT_PREFIX.unpack_from(payload, offset)
        offset += _RPC_ARGUMENT_PREFIX.size
        declared = list(NetworkValueType).index(argument.type) + 1
        if type_code != declared or size > argument.max_bytes or offset + size > len(payload):
            raise ValueError("RPC argument does not match its schema")
        values.append(
            _decode_value(
                _rpc_value_spec(index, argument), payload[offset : offset + size]
            )
        )
        offset += size
    if offset != len(payload):
        raise ValueError("RPC payload has trailing bytes")
    return sequence, tuple(values)


def _decode(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < _HEADER.size or len(frame) > _HEADER.size + _VALUE_PREFIX.size + _MAX_VALUE_BYTES:
        raise ValueError("invalid replication frame size")
    magic, version, message_type, flags, size = _HEADER.unpack_from(frame)
    if magic != _MAGIC or version != _WIRE_VERSION or flags != 0:
        raise ValueError("invalid replication frame envelope")
    if message_type not in (
        _BEGIN,
        _SPAWN,
        _DESPAWN,
        _END,
        _VALUE,
        _TRANSFORM,
        _RPC,
        _RESYNC,
        _TRANSFORM_ACK,
        _TRANSFORM_DELTA,
        _BASELINE_REQUEST,
        _TRANSFORM_ACK_BATCH,
    ):
        raise ValueError("unknown replication frame type")
    if message_type not in (
        _VALUE,
        _TRANSFORM,
        _TRANSFORM_DELTA,
        _RPC,
        _TRANSFORM_ACK_BATCH,
    ) and len(frame) > _MAX_FRAME_SIZE:
        raise ValueError("lifecycle frame exceeds its fixed bound")
    if message_type == _TRANSFORM and len(frame) != _HEADER.size + _TRANSFORM_PAYLOAD.size:
        raise ValueError("invalid transform frame size")
    if message_type == _TRANSFORM_DELTA and len(frame) != _HEADER.size + _TRANSFORM_DELTA_PAYLOAD.size:
        raise ValueError("invalid transform delta frame size")
    if message_type == _RPC and len(frame) > _HEADER.size + _MAX_RPC_BYTES:
        raise ValueError("RPC frame exceeds its total byte bound")
    if message_type == _TRANSFORM_ACK_BATCH and len(frame) > (
        _HEADER.size
        + _TRANSFORM_ACK_BATCH_PREFIX.size
        + _MAX_TRANSFORM_ACK_BATCH * _TRANSFORM_ACK_PAYLOAD.size
    ):
        raise ValueError("transform ACK batch exceeds its fixed bound")
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
        "_transform_budget_bytes_per_second",
        "_transform_budget_burst_bytes",
        "_transform_tick_rate",
        "_transform_tokens",
        "_transform_baselines",
        "_transform_sent_history",
        "_baseline_request_sequences",
        "_priority",
        "_spatial_interest",
        "_next_id",
        "_objects",
        "_owners",
        "_ready_connections",
        "_old_connect",
        "_old_disconnect",
        "_old_message",
        "_registry",
        "_resync_last_sequences",
        "_resync_last_times",
        "_server",
        "_snapshot_epoch",
        "_last_transform_flush",
        "_last_transform_tick",
        "_relevance_filter",
        "_rpc_executed",
        "_rpc_last_sequences",
        "_rpc_rate_limited",
        "_rpc_received",
        "_rpc_sequence",
        "_rpc_windows",
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
        priority: Callable[[ConnectionId, ReplicatedObject], float] | None = None,
        spatial_interest: SpatialInterest | None = None,
        transform_budget_bytes_per_second: int = 256 * 1024,
        transform_budget_burst_bytes: int = 64 * 1024,
        transform_tick_rate: int = 60,
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
        if priority is not None and not callable(priority):
            raise TypeError("priority must be callable")
        if spatial_interest is not None and not isinstance(
            spatial_interest, SpatialInterest
        ):
            raise TypeError("spatial_interest must be a SpatialInterest")
        for name, value, minimum in (
            ("transform_budget_bytes_per_second", transform_budget_bytes_per_second, 1024),
            ("transform_budget_burst_bytes", transform_budget_burst_bytes, _HEADER.size + _TRANSFORM_PAYLOAD.size),
            ("transform_tick_rate", transform_tick_rate, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < minimum:
                raise ValueError(f"{name} is below its supported minimum")
        if server in _attached_servers:
            raise RuntimeError("this server already has a replication owner")
        if server.connections:
            raise RuntimeError("attach replication before clients connect")
        registry.freeze()
        self._server = server
        self._registry = registry
        self._resync_last_sequences: dict[ConnectionId, int] = {}
        self._resync_last_times: dict[ConnectionId, float] = {}
        self._max_objects = max_objects
        self._max_transform_sends = max_transform_sends
        self._transform_budget_bytes_per_second = transform_budget_bytes_per_second
        self._transform_budget_burst_bytes = transform_budget_burst_bytes
        self._transform_tick_rate = transform_tick_rate
        self._transform_tokens: dict[ConnectionId, float] = {}
        self._transform_baselines: dict[
            tuple[ConnectionId, NetworkObjectId], TransformSnapshot
        ] = {}
        self._transform_sent_history: dict[
            tuple[ConnectionId, NetworkObjectId], deque[TransformSnapshot]
        ] = {}
        self._baseline_request_sequences: dict[ConnectionId, int] = {}
        self._priority = priority
        self._spatial_interest = spatial_interest
        self._objects: dict[NetworkObjectId, ReplicatedObject] = {}
        self._owners: dict[NetworkObjectId, ConnectionId | None] = {}
        self._ready_connections: set[ConnectionId] = set()
        self._next_id = 1
        self._snapshot_epoch = 0
        self._transform_sequence = 0
        self._last_transform_tick: int | None = None
        self._relevance_filter = relevance_filter
        self._rpc_sequence = 0
        self._rpc_last_sequences: dict[ConnectionId, int] = {}
        self._rpc_windows: dict[
            tuple[ConnectionId, NetworkObjectId, int], deque[float]
        ] = {}
        self._rpc_received = 0
        self._rpc_executed = 0
        self._rpc_rate_limited = 0
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

    @property
    def rpc_stats(self) -> RpcStats:
        return RpcStats(
            self._rpc_received, self._rpc_executed, self._rpc_rate_limited
        )

    def set_relevance_filter(
        self,
        relevance_filter: Callable[[ConnectionId, ReplicatedObject], bool] | None,
    ) -> None:
        if relevance_filter is not None and not callable(relevance_filter):
            raise TypeError("relevance_filter must be callable")
        self._relevance_filter = relevance_filter

    def set_priority(
        self,
        priority: Callable[[ConnectionId, ReplicatedObject], float] | None,
    ) -> None:
        if priority is not None and not callable(priority):
            raise TypeError("priority must be callable")
        self._priority = priority

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
        self._owners[identifier] = None
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
        self._owners.pop(identifier, None)
        for key in [key for key in self._rpc_windows if key[1] == identifier]:
            del self._rpc_windows[key]
        for key in [key for key in self._variables if key[0] == identifier]:
            del self._variables[key]
        for key in [key for key in self._transform_baselines if key[1] == identifier]:
            del self._transform_baselines[key]
        for key in [key for key in self._transform_sent_history if key[1] == identifier]:
            del self._transform_sent_history[key]
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

    def set_owner(
        self,
        object_id: NetworkObjectId | int,
        connection: ConnectionId | None,
    ) -> None:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        if identifier not in self._objects:
            raise KeyError(f"unknown network object ID {identifier.value}")
        if connection is not None:
            if not isinstance(connection, ConnectionId):
                raise TypeError("connection must be an easy3d.network.ConnectionId")
            if connection not in self._ready_connections:
                raise ValueError("owner connection is not established")
        self._owners[identifier] = connection

    def owner(self, object_id: NetworkObjectId | int) -> ConnectionId | None:
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            return self._owners[identifier]
        except KeyError as error:
            raise KeyError(f"unknown network object ID {identifier.value}") from error

    def call_client(
        self,
        connection: ConnectionId,
        object_id: NetworkObjectId | int,
        rpc_id: int,
        *arguments: object,
    ) -> SendStatus:
        if connection not in self._ready_connections:
            return SendStatus.INVALID_CONNECTION
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            replicated = self._objects[identifier]
        except KeyError as error:
            raise KeyError(f"unknown network object ID {identifier.value}") from error
        spec = self._registry.rpc(replicated.prefab_id, rpc_id)
        if spec.direction is not RpcDirection.SERVER_TO_CLIENT:
            raise PermissionError("RPC direction does not allow server-to-client calls")
        if self._rpc_sequence == 2**64 - 1:
            raise NetworkError("RPC invocation sequence space is exhausted")
        self._rpc_sequence += 1
        return self._server.send(
            connection,
            _rpc_frame(identifier, spec, self._rpc_sequence, arguments),
            delivery=spec.delivery,
        )

    def broadcast_rpc(
        self,
        object_id: NetworkObjectId | int,
        rpc_id: int,
        *arguments: object,
    ) -> dict[ConnectionId, SendStatus]:
        return {
            connection: self.call_client(connection, object_id, rpc_id, *arguments)
            for connection in sorted(self._ready_connections)
        }

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
        connections = tuple(sorted(self._ready_connections))
        if len(transform_objects) * len(connections) > self._max_transform_sends:
            raise NetworkError("transform snapshot send bound is exceeded")
        sequence = self._transform_sequence + 1
        filtered = 0
        frames = {
            item.id: _transform_frame(item, sequence, tick)
            for item in transform_objects
        }
        snapshots = {
            identifier: _snapshot_from_frame(frame)
            for identifier, frame in frames.items()
        }
        # A synchronized fan-out commonly has many connections acknowledging
        # the exact same immutable baseline object. Delta encoding and its
        # quantized reconstruction are therefore identical. Reuse that work
        # within this flush; object identity keeps divergent baselines safely
        # separate even when they happen to carry the same sequence number.
        delta_cache: dict[
            tuple[NetworkObjectId, int],
            tuple[bytes, TransformSnapshot] | None,
        ] = {}
        tick_delta = (
            1
            if self._last_transform_tick is None
            else max(0, tick - self._last_transform_tick)
        )
        queued = 0
        backpressured = 0
        budget_deferred = 0
        full_snapshots = 0
        delta_snapshots = 0
        bytes_queued = 0
        for connection in connections:
            tokens = min(
                float(self._transform_budget_burst_bytes),
                self._transform_tokens.get(
                    connection, float(self._transform_budget_burst_bytes)
                )
                + self._transform_budget_bytes_per_second
                * tick_delta
                / self._transform_tick_rate,
            )
            relevant: list[tuple[float, ReplicatedObject]] = []
            for item in transform_objects:
                is_relevant = (
                    self._relevance_filter is None
                    or self._relevance_filter(connection, item)
                ) and (
                    self._spatial_interest is None
                    or self._spatial_interest.relevant(connection, item)
                )
                if not is_relevant:
                    filtered += 1
                    continue
                priority_value = 0.0
                if self._spatial_interest is not None:
                    priority_value += self._spatial_interest.priority(connection, item)
                if self._priority is not None:
                    declared = float(self._priority(connection, item))
                    if not math.isfinite(declared):
                        raise ValueError("transform priority must be finite")
                    priority_value += declared
                relevant.append((priority_value, item))
            relevant.sort(key=lambda entry: (-entry[0], entry[1].id.value))
            for _priority, item in relevant:
                current = snapshots[item.id]
                baseline = self._transform_baselines.get((connection, item.id))
                if baseline is None:
                    delta = None
                else:
                    cache_key = (item.id, id(baseline))
                    if cache_key not in delta_cache:
                        delta_cache[cache_key] = _transform_delta_frame(
                            item.id, current, baseline
                        )
                    delta = delta_cache[cache_key]
                is_delta = delta is not None
                transmitted = current
                if delta is None:
                    frame = frames[item.id]
                else:
                    frame, transmitted = delta
                if len(frame) > tokens:
                    budget_deferred += 1
                    continue
                status = self._server.send(
                    connection, frame, delivery=Delivery.UNRELIABLE
                )
                if status is SendStatus.QUEUED:
                    queued += 1
                    bytes_queued += len(frame)
                    tokens -= len(frame)
                    if is_delta:
                        delta_snapshots += 1
                    else:
                        full_snapshots += 1
                    history = self._transform_sent_history.setdefault(
                        (connection, item.id), deque(maxlen=32)
                    )
                    history.append(transmitted)
                else:
                    backpressured += 1
            self._transform_tokens[connection] = tokens
        self._transform_sequence = sequence
        self._last_transform_tick = tick
        self._last_transform_flush = TransformFlushStats(
            sequence,
            tick,
            queued,
            filtered,
            backpressured,
            budget_deferred,
            full_snapshots,
            delta_snapshots,
            bytes_queued,
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
            self._owners.clear()
            self._variables.clear()
        self._ready_connections.clear()
        self._closed = True

    def _on_connect(self, server: Server, connection: ConnectionId) -> None:
        self._transform_tokens[connection] = float(
            self._transform_budget_burst_bytes
        )
        if self._send_snapshot(connection):
            self._ready_connections.add(connection)
        if connection in self._ready_connections and self._old_connect is not None:
            self._old_connect(server, connection)

    def _on_disconnect(self, server: Server, event: NetworkEvent) -> None:
        self._ready_connections.discard(event.connection)
        # A whole-server stop makes every native connection inactive before
        # Python receives the queued disconnect callbacks. Reconcile the
        # replication recipients now so user teardown (for example despawning
        # this player's object) cannot broadcast to already-closed peers.
        self._ready_connections.intersection_update(server.connections)
        for identifier, owner in tuple(self._owners.items()):
            if owner == event.connection:
                self._owners[identifier] = None
        self._rpc_last_sequences.pop(event.connection, None)
        self._resync_last_sequences.pop(event.connection, None)
        self._resync_last_times.pop(event.connection, None)
        self._baseline_request_sequences.pop(event.connection, None)
        self._transform_tokens.pop(event.connection, None)
        for key in [key for key in self._transform_baselines if key[0] == event.connection]:
            del self._transform_baselines[key]
        for key in [key for key in self._transform_sent_history if key[0] == event.connection]:
            del self._transform_sent_history[key]
        if self._spatial_interest is not None:
            self._spatial_interest.remove_observer(event.connection)
        for key in [key for key in self._rpc_windows if key[0] == event.connection]:
            del self._rpc_windows[key]
        if self._old_disconnect is not None:
            self._old_disconnect(server, event)

    def _on_message(self, server: Server, event: NetworkEvent) -> None:
        if event.payload.startswith(_MAGIC):
            try:
                message_type, payload = _decode(event.payload)
                if message_type == _RPC:
                    self._receive_rpc(event.connection, payload)
                elif message_type == _RESYNC:
                    self._receive_resync(event.connection, payload)
                elif message_type == _TRANSFORM_ACK:
                    self._receive_transform_ack(event.connection, payload)
                elif message_type == _TRANSFORM_ACK_BATCH:
                    self._receive_transform_ack_batch(event.connection, payload)
                elif message_type == _BASELINE_REQUEST:
                    self._receive_baseline_request(event.connection, payload)
                else:
                    raise PermissionError("client-authored replication is forbidden")
            except (KeyError, PermissionError, TypeError, ValueError) as error:
                server.disconnect(event.connection, f"invalid replication control: {error}")
            return
        if self._old_message is not None:
            self._old_message(server, event)

    def _receive_resync(self, connection: ConnectionId, payload: bytes) -> None:
        if connection not in self._ready_connections:
            raise PermissionError("resync arrived before replication snapshot readiness")
        if len(payload) != _RESYNC_PAYLOAD.size:
            raise ValueError("invalid resync payload size")
        (sequence,) = _RESYNC_PAYLOAD.unpack(payload)
        if sequence == 0 or sequence <= self._resync_last_sequences.get(connection, 0):
            raise ValueError("resync sequence is stale or duplicated")
        self._resync_last_sequences[connection] = sequence
        now = time.monotonic()
        previous = self._resync_last_times.get(connection)
        if previous is not None and now - previous < 0.25:
            return
        self._resync_last_times[connection] = now
        self._ready_connections.discard(connection)
        for key in [key for key in self._transform_baselines if key[0] == connection]:
            del self._transform_baselines[key]
        for key in [key for key in self._transform_sent_history if key[0] == connection]:
            del self._transform_sent_history[key]
        if self._send_snapshot(connection):
            self._ready_connections.add(connection)

    def _receive_transform_ack(
        self, connection: ConnectionId, payload: bytes
    ) -> None:
        if connection not in self._ready_connections:
            raise PermissionError("transform ACK arrived before snapshot readiness")
        if len(payload) != _TRANSFORM_ACK_PAYLOAD.size:
            raise ValueError("invalid transform ACK size")
        object_value, sequence = _TRANSFORM_ACK_PAYLOAD.unpack(payload)
        self._apply_transform_ack(connection, object_value, sequence)

    def _receive_transform_ack_batch(
        self, connection: ConnectionId, payload: bytes
    ) -> None:
        if connection not in self._ready_connections:
            raise PermissionError("transform ACK arrived before snapshot readiness")
        if len(payload) < _TRANSFORM_ACK_BATCH_PREFIX.size:
            raise ValueError("invalid transform ACK batch size")
        (count,) = _TRANSFORM_ACK_BATCH_PREFIX.unpack_from(payload)
        if not 1 <= count <= _MAX_TRANSFORM_ACK_BATCH or len(payload) != (
            _TRANSFORM_ACK_BATCH_PREFIX.size + count * _TRANSFORM_ACK_PAYLOAD.size
        ):
            raise ValueError("invalid transform ACK batch bounds")
        offset = _TRANSFORM_ACK_BATCH_PREFIX.size
        for _ in range(count):
            object_value, sequence = _TRANSFORM_ACK_PAYLOAD.unpack_from(payload, offset)
            offset += _TRANSFORM_ACK_PAYLOAD.size
            self._apply_transform_ack(connection, object_value, sequence)

    def _apply_transform_ack(
        self, connection: ConnectionId, object_value: int, sequence: int
    ) -> None:
        identifier = NetworkObjectId(object_value)
        replicated = self._objects.get(identifier)
        if replicated is None or not self._registry.has_transform(replicated.prefab_id):
            raise ValueError("transform ACK references an unknown transform")
        if sequence > self._transform_sequence:
            raise ValueError("transform ACK sequence is from the future")
        history = self._transform_sent_history.get((connection, identifier), ())
        for snapshot in reversed(history):
            if snapshot.sequence == sequence:
                current = self._transform_baselines.get((connection, identifier))
                if current is None or snapshot.sequence >= current.sequence:
                    self._transform_baselines[(connection, identifier)] = snapshot
                return

    def _receive_baseline_request(
        self, connection: ConnectionId, payload: bytes
    ) -> None:
        if connection not in self._ready_connections:
            raise PermissionError("baseline request arrived before snapshot readiness")
        if len(payload) != _BASELINE_REQUEST_PAYLOAD.size:
            raise ValueError("invalid baseline request size")
        request_sequence, object_value = _BASELINE_REQUEST_PAYLOAD.unpack(payload)
        last = self._baseline_request_sequences.get(connection, 0)
        if request_sequence == 0 or request_sequence <= last:
            raise ValueError("baseline request sequence is stale or duplicated")
        identifier = NetworkObjectId(object_value)
        replicated = self._objects.get(identifier)
        if replicated is None or not self._registry.has_transform(replicated.prefab_id):
            raise ValueError("baseline request references an unknown transform")
        self._baseline_request_sequences[connection] = request_sequence
        self._transform_baselines.pop((connection, identifier), None)

    def _receive_rpc(self, connection: ConnectionId, payload: bytes) -> None:
        if connection not in self._ready_connections:
            raise PermissionError("RPC arrived before replication snapshot readiness")
        if len(payload) < _RPC_PREFIX.size:
            raise ValueError("truncated RPC prefix")
        object_value, rpc_id, sequence, _count = _RPC_PREFIX.unpack_from(payload)
        identifier = NetworkObjectId(object_value)
        try:
            replicated = self._objects[identifier]
        except KeyError as error:
            raise ValueError("RPC references an unknown object") from error
        spec = self._registry.rpc(replicated.prefab_id, rpc_id)
        if spec.direction is not RpcDirection.CLIENT_TO_SERVER:
            raise PermissionError("RPC direction does not allow client-to-server calls")
        if spec.require_owner and self._owners[identifier] != connection:
            raise PermissionError("RPC sender does not own the object")
        last_sequence = self._rpc_last_sequences.get(connection, 0)
        if sequence <= last_sequence:
            raise ValueError("RPC invocation sequence is stale or duplicated")
        decoded_sequence, arguments = _decode_rpc_payload(spec, payload)
        if decoded_sequence != sequence:
            raise ValueError("RPC sequence decoding mismatch")
        self._rpc_last_sequences[connection] = sequence
        self._rpc_received += 1
        key = (connection, identifier, spec.id)
        window = self._rpc_windows.setdefault(key, deque())
        now = time.monotonic()
        while window and window[0] <= now - 1.0:
            window.popleft()
        if len(window) >= spec.rate_limit:
            self._rpc_rate_limited += 1
            return
        window.append(now)
        spec.handler(replicated.entity, connection, *arguments)
        self._rpc_executed += 1

    def _send_snapshot(self, connection: ConnectionId) -> bool:
        if self._snapshot_epoch == 2**64 - 1:
            self._server.disconnect(connection, "replication snapshot epoch exhausted")
            return False
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
            return False
        for item in self.objects:
            spawn = _frame(
                _SPAWN,
                _SPAWN_PAYLOAD.pack(item.id.value, item.prefab_id.value),
            )
            if self._server.send(connection, spawn) is not SendStatus.QUEUED:
                self._server.disconnect(connection, "replication snapshot backpressure")
                return False
            for spec in self._registry.variables(item.prefab_id):
                value = _value_frame(item.id, self._variables[(item.id, spec.id)])
                if self._server.send(connection, value) is not SendStatus.QUEUED:
                    self._server.disconnect(
                        connection, "replication snapshot backpressure"
                    )
                    return False
            if self._registry.has_transform(item.prefab_id):
                try:
                    relevant = (
                        self._relevance_filter is None
                        or self._relevance_filter(connection, item)
                    ) and (
                        self._spatial_interest is None
                        or self._spatial_interest.relevant(connection, item)
                    )
                except Exception:
                    self._server.disconnect(connection, "replication relevance callback failed")
                    return False
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
                        return False
                    snapshot = _snapshot_from_frame(transform)
                    history = self._transform_sent_history.setdefault(
                        (connection, item.id), deque(maxlen=32)
                    )
                    history.append(snapshot)
        end = _frame(_END, _END_PAYLOAD.pack(epoch))
        if self._server.send(connection, end) is not SendStatus.QUEUED:
            self._server.disconnect(connection, "replication snapshot backpressure")
            return False
        return True

    def _broadcast(self, frame: bytes) -> None:
        for connection in tuple(sorted(self._ready_connections)):
            status = self._server.send(connection, frame)
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
        "_full_transforms",
        "_delta_transforms",
        "_transform_acks_sent",
        "_pending_transform_acks",
        "_baseline_requests",
        "_baseline_request_sequence",
        "_max_objects",
        "_max_transform_samples",
        "_objects",
        "_received_count",
        "_received_transforms",
        "_registry",
        "_resync_sequence",
        "_rpc_executed",
        "_rpc_last_sequence",
        "_rpc_received",
        "_rpc_sequence",
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
        self._resync_sequence = 0
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
        self._full_transforms = 0
        self._delta_transforms = 0
        self._transform_acks_sent = 0
        self._pending_transform_acks: dict[NetworkObjectId, int] = {}
        self._baseline_requests = 0
        self._baseline_request_sequence = 0
        self._rpc_sequence = 0
        self._rpc_last_sequence = 0
        self._rpc_received = 0
        self._rpc_executed = 0

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

    @property
    def delta_baseline_stats(self) -> DeltaBaselineStats:
        return DeltaBaselineStats(
            self._full_transforms,
            self._delta_transforms,
            self._transform_acks_sent,
            self._baseline_requests,
        )

    @property
    def rpc_stats(self) -> RpcStats:
        return RpcStats(self._rpc_received, self._rpc_executed, 0)

    def poll(self, maximum_events: int = 256) -> tuple[NetworkEvent, ...]:
        application: list[NetworkEvent] = []
        for event in self._client.poll(maximum_events):
            if event.type is EventType.DISCONNECTED:
                self.clear()
                application.append(event)
            elif event.type is EventType.MESSAGE and event.payload.startswith(_MAGIC):
                try:
                    self._apply(event.payload)
                except (
                    KeyError,
                    PermissionError,
                    TypeError,
                    ValueError,
                    RuntimeError,
                ) as error:
                    if self._client.connection is not None:
                        self._client.disconnect("invalid replication lifecycle frame")
                    self.clear()
                    raise NetworkError(f"invalid replication lifecycle frame: {error}") from error
            else:
                application.append(event)
        self._flush_transform_acks()
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

    def request_resync(self) -> SendStatus:
        """Request one complete authoritative snapshot on the reliable channel."""

        if not self._synchronized or self._client.connection is None:
            return SendStatus.INVALID_CONNECTION
        if self._resync_sequence == 2**64 - 1:
            raise NetworkError("resync request sequence space is exhausted")
        self._resync_sequence += 1
        return self._client.send(
            _resync_frame(self._resync_sequence), delivery=Delivery.RELIABLE
        )

    def call_server(
        self,
        object_id: NetworkObjectId | int,
        rpc_id: int,
        *arguments: object,
    ) -> SendStatus:
        if not self._synchronized or self._client.connection is None:
            return SendStatus.INVALID_CONNECTION
        identifier = (
            object_id
            if isinstance(object_id, NetworkObjectId)
            else NetworkObjectId(object_id)
        )
        try:
            replicated = self._objects[identifier]
        except KeyError as error:
            raise KeyError(f"unknown network object ID {identifier.value}") from error
        spec = self._registry.rpc(replicated.prefab_id, rpc_id)
        if spec.direction is not RpcDirection.CLIENT_TO_SERVER:
            raise PermissionError("RPC direction does not allow client-to-server calls")
        if self._rpc_sequence == 2**64 - 1:
            raise NetworkError("RPC invocation sequence space is exhausted")
        self._rpc_sequence += 1
        return self._client.send(
            _rpc_frame(identifier, spec, self._rpc_sequence, arguments),
            delivery=spec.delivery,
        )

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
        self._pending_transform_acks.clear()
        self._snapshot_epoch = None
        self._snapshot_fields.clear()
        self._expected_count = 0
        self._received_count = 0
        self._synchronized = False
        self._rpc_last_sequence = 0

    def _store_transform(
        self, identifier: NetworkObjectId, snapshot: TransformSnapshot
    ) -> bool:
        history = self._transform_history.setdefault(
            identifier, deque(maxlen=self._max_transform_samples)
        )
        if history and (
            snapshot.sequence <= history[-1].sequence
            or snapshot.tick < history[-1].tick
        ):
            self._stale_transforms += 1
            return False
        if history and snapshot.tick == history[-1].tick:
            history[-1] = snapshot
        else:
            if len(history) == self._max_transform_samples:
                self._history_evictions += 1
            history.append(snapshot)
        self._pending_transform_acks[identifier] = snapshot.sequence
        return True

    def _flush_transform_acks(self) -> None:
        """Coalesce replaceable per-object ACK state into bounded datagrams."""

        if not self._pending_transform_acks or self._client.connection is None:
            return
        pending = tuple(sorted(self._pending_transform_acks.items()))
        for offset in range(0, len(pending), _MAX_TRANSFORM_ACK_BATCH):
            chunk = pending[offset : offset + _MAX_TRANSFORM_ACK_BATCH]
            status = self._client.send(
                _transform_ack_batch_frame(chunk),
                # Later ACKs supersede lost ACKs; reliable retransmission would
                # only add stale control traffic to a replaceable state stream.
                delivery=Delivery.UNRELIABLE,
            )
            if status is not SendStatus.QUEUED:
                break
            self._transform_acks_sent += len(chunk)
            for identifier, sequence in chunk:
                if self._pending_transform_acks.get(identifier) == sequence:
                    del self._pending_transform_acks[identifier]

    def _request_transform_baseline(self, identifier: NetworkObjectId) -> None:
        if self._baseline_request_sequence == 2**64 - 1:
            raise NetworkError("baseline request sequence space is exhausted")
        self._baseline_request_sequence += 1
        status = self._client.send(
            _baseline_request_frame(self._baseline_request_sequence, identifier),
            delivery=Delivery.RELIABLE,
        )
        if status is SendStatus.QUEUED:
            self._baseline_requests += 1

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
                if version == variable.version:
                    if value != variable.value:
                        raise ValueError("NetworkVar duplicate version conflicts with state")
                    return
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
            self._full_transforms += 1
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
            snapshot = TransformSnapshot(tick, sequence, position, rotation, scale)
            self._store_transform(identifier, snapshot)
            return
        if message_type == _TRANSFORM_DELTA:
            unpacked = _TRANSFORM_DELTA_PAYLOAD.unpack(payload)
            object_value, sequence, tick, baseline_sequence = unpacked[:4]
            identifier = NetworkObjectId(object_value)
            replicated = self._objects.get(identifier)
            self._received_transforms += 1
            self._delta_transforms += 1
            if replicated is None:
                self._unknown_transforms += 1
                return
            if not self._registry.has_transform(replicated.prefab_id):
                raise ValueError("transform delta is not declared by the prefab schema")
            history = self._transform_history.get(identifier, ())
            baseline = next(
                (
                    snapshot
                    for snapshot in reversed(history)
                    if snapshot.sequence == baseline_sequence
                ),
                None,
            )
            if baseline is None:
                self._request_transform_baseline(identifier)
                return
            values = unpacked[4:]
            base_position = tuple(baseline.position)
            base_rotation = tuple(baseline.rotation)
            base_scale = tuple(baseline.scale)
            position = Vec3(
                tuple(base_position[index] + values[index] / 100.0 for index in range(3))
            )
            try:
                rotation = Quat(
                    tuple(
                        base_rotation[index] + values[index + 3] / 16000.0
                        for index in range(4)
                    )
                ).normalized()
            except ValueError as error:
                raise ValueError("transform delta reconstructs a zero quaternion") from error
            scale = Vec3(
                tuple(base_scale[index] + values[index + 7] / 1000.0 for index in range(3))
            )
            if any(component == 0.0 for component in scale):
                raise ValueError("transform delta reconstructs zero scale")
            self._store_transform(
                identifier,
                TransformSnapshot(tick, sequence, position, rotation, scale),
            )
            return
        if message_type == _RPC:
            if not self._synchronized:
                raise ValueError("RPC arrived before the initial snapshot completed")
            if len(payload) < _RPC_PREFIX.size:
                raise ValueError("truncated RPC prefix")
            object_value, rpc_id, sequence, _count = _RPC_PREFIX.unpack_from(payload)
            identifier = NetworkObjectId(object_value)
            try:
                replicated = self._objects[identifier]
            except KeyError as error:
                raise ValueError("RPC references an unknown object") from error
            spec = self._registry.rpc(replicated.prefab_id, rpc_id)
            if spec.direction is not RpcDirection.SERVER_TO_CLIENT:
                raise PermissionError("RPC direction does not allow server-to-client calls")
            if sequence <= self._rpc_last_sequence:
                raise ValueError("RPC invocation sequence is stale or duplicated")
            decoded_sequence, arguments = _decode_rpc_payload(spec, payload)
            self._rpc_last_sequence = decoded_sequence
            self._rpc_received += 1
            spec.handler(replicated.entity, *arguments)
            self._rpc_executed += 1
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
    "DeltaBaselineStats",
    "NetworkObjectId",
    "NetworkTransform",
    "NetworkValueType",
    "NetworkVar",
    "NetworkVarSpec",
    "PrefabId",
    "PrefabRegistration",
    "PrefabRegistry",
    "ReplicatedObject",
    "RpcArgumentSpec",
    "RpcDirection",
    "RpcSpec",
    "RpcStats",
    "ServerReplication",
    "SpatialInterest",
    "TransformFlushStats",
    "TransformReplicationStats",
    "TransformSnapshot",
]
