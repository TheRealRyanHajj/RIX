"""Server-owned network object lifecycle and late-join snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import struct
import unicodedata
from weakref import WeakKeyDictionary

from ._easy3d import NetworkError
from .entity import Entity
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
_HEADER = struct.Struct("<4sHBBI")
_BEGIN_PAYLOAD = struct.Struct("<QII16s")
_SPAWN_PAYLOAD = struct.Struct("<QI")
_DESPAWN_PAYLOAD = struct.Struct("<Q")
_END_PAYLOAD = struct.Struct("<Q")
_MAX_FRAME_SIZE = 64


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


@dataclass(frozen=True, slots=True)
class PrefabRegistration:
    id: PrefabId
    name: str
    factory: PrefabFactory


class PrefabRegistry:
    """Bounded explicit prefab/schema mapping shared by authority and clients."""

    __slots__ = ("_capacity", "_entries", "_frozen", "_names", "_schema_version")

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
        self._names.add(name)
        return registration

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


def _decode(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < _HEADER.size or len(frame) > _MAX_FRAME_SIZE:
        raise ValueError("invalid replication frame size")
    magic, version, message_type, flags, size = _HEADER.unpack_from(frame)
    if magic != _MAGIC or version != _WIRE_VERSION or flags != 0:
        raise ValueError("invalid replication frame envelope")
    if message_type not in (_BEGIN, _SPAWN, _DESPAWN, _END):
        raise ValueError("unknown replication frame type")
    if size != len(frame) - _HEADER.size:
        raise ValueError("invalid replication payload length")
    return message_type, frame[_HEADER.size :]


_attached_servers: WeakKeyDictionary[Server, bool] = WeakKeyDictionary()


class ServerReplication:
    """Server-only allocator and lifecycle broadcaster."""

    __slots__ = (
        "_closed",
        "_max_objects",
        "_next_id",
        "_objects",
        "_old_connect",
        "_old_disconnect",
        "_old_message",
        "_registry",
        "_server",
        "_snapshot_epoch",
        "__weakref__",
    )

    def __init__(
        self,
        server: Server,
        registry: PrefabRegistry,
        *,
        max_objects: int = 65536,
    ) -> None:
        if not isinstance(server, Server):
            raise TypeError("server must be an easy3d.Server")
        if not isinstance(registry, PrefabRegistry):
            raise TypeError("registry must be a PrefabRegistry")
        if isinstance(max_objects, bool) or not isinstance(max_objects, int):
            raise TypeError("max_objects must be an integer")
        if not 1 <= max_objects <= 1_000_000:
            raise ValueError("max_objects must be in [1, 1000000]")
        if server in _attached_servers:
            raise RuntimeError("this server already has a replication owner")
        if server.connections:
            raise RuntimeError("attach replication before clients connect")
        registry.freeze()
        self._server = server
        self._registry = registry
        self._max_objects = max_objects
        self._objects: dict[NetworkObjectId, ReplicatedObject] = {}
        self._next_id = 1
        self._snapshot_epoch = 0
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
        if replicated.entity.is_alive:
            replicated.entity.destroy()
        return replicated.entity

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
        frames = [begin]
        frames.extend(
            _frame(_SPAWN, _SPAWN_PAYLOAD.pack(item.id.value, item.prefab_id.value))
            for item in self.objects
        )
        frames.append(_frame(_END, _END_PAYLOAD.pack(epoch)))
        for frame in frames:
            if self._server.send(connection, frame) is not SendStatus.QUEUED:
                self._server.disconnect(connection, "replication snapshot backpressure")
                return

    def _broadcast(self, frame: bytes) -> None:
        for connection, status in self._server.broadcast(frame).items():
            if status is not SendStatus.QUEUED:
                self._server.disconnect(connection, "replication update backpressure")


class ClientReplication:
    """Apply validated authority lifecycle frames to one client scene."""

    __slots__ = (
        "_client",
        "_expected_count",
        "_max_objects",
        "_objects",
        "_received_count",
        "_registry",
        "_scene",
        "_snapshot_epoch",
        "_synchronized",
    )

    def __init__(
        self,
        client: Client,
        scene: Scene,
        registry: PrefabRegistry,
        *,
        max_objects: int = 65536,
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
        registry.freeze()
        self._client = client
        self._scene = scene
        self._registry = registry
        self._max_objects = max_objects
        self._objects: dict[NetworkObjectId, ReplicatedObject] = {}
        self._snapshot_epoch: int | None = None
        self._expected_count = 0
        self._received_count = 0
        self._synchronized = False

    @property
    def objects(self) -> tuple[ReplicatedObject, ...]:
        return tuple(self._objects[key] for key in sorted(self._objects))

    @property
    def is_synchronized(self) -> bool:
        return self._synchronized

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

    def clear(self) -> None:
        for replicated in self.objects:
            if replicated.entity.is_alive:
                replicated.entity.destroy()
        self._objects.clear()
        self._snapshot_epoch = None
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
            return
        if len(payload) != _END_PAYLOAD.size or self._snapshot_epoch is None:
            raise ValueError("invalid snapshot-end state or size")
        (epoch,) = _END_PAYLOAD.unpack(payload)
        if epoch != self._snapshot_epoch or self._received_count != self._expected_count:
            raise ValueError("snapshot end does not match its declaration")
        self._snapshot_epoch = None
        self._synchronized = True


__all__ = [
    "ClientReplication",
    "NetworkObjectId",
    "PrefabId",
    "PrefabRegistration",
    "PrefabRegistry",
    "ReplicatedObject",
    "ServerReplication",
]
