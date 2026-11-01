"""Scene ownership and context-managed entity construction."""

from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar, Token
from types import TracebackType
from typing import TYPE_CHECKING, Callable
import weakref

from ._easy3d import EntityHandle, _NativeScene
from .camera import Camera
from .components import ColorValue, normalize_color
from .math import Quat, Vec3

if TYPE_CHECKING:
    from .entity import Entity


_current_scene: ContextVar[Scene | None] = ContextVar("easy3d_current_scene", default=None)


class Scene:
    """Owns a native world and every entity created within it.

    Use ``with scene:`` to make construction concise. There is intentionally no
    process-global default scene outside an explicit context.
    """

    def __init__(self, name: str = "Scene") -> None:
        if not isinstance(name, str):
            raise TypeError("scene name must be a string")
        self._native = _NativeScene(name)
        self._closed = False
        self._context_tokens: list[Token[Scene | None]] = []
        self._owner: weakref.ReferenceType[object] | None = None
        self._script_entities: dict[int, Entity] = {}
        self._deferred_destroy: dict[int, Entity] = {}
        self._deferred_clear = False

    @classmethod
    def current(cls) -> Scene:
        scene = _current_scene.get()
        if scene is None:
            raise RuntimeError(
                "no active scene; pass scene=... or construct the entity inside 'with scene:'"
            )
        scene._require_open()
        return scene

    @property
    def name(self) -> str:
        return self._native.name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("scene name must be a string")
        self._require_mutable()
        self._native.name = value

    @property
    def active(self) -> bool:
        return self._native.active

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def world_id(self) -> int:
        return self._native.world_id

    @property
    def entity_count(self) -> int:
        return self._native.entity_count

    @property
    def camera(self) -> Camera:
        position, rotation, fov, near, far, projection, orthographic_height = (
            self._native.camera_info()
        )
        return Camera(
            position=position,
            rotation=Quat(rotation).to_euler(),
            vertical_fov_degrees=fov,
            near_plane=near,
            far_plane=far,
            projection=projection,
            orthographic_height=orthographic_height,
        )

    @camera.setter
    def camera(self, value: Camera) -> None:
        if not isinstance(value, Camera):
            raise TypeError("camera must be an easy3d.Camera")
        self._require_mutable()
        self._native.set_camera(
            tuple(value.position),
            tuple(value.quaternion),
            value.vertical_fov_degrees,
            value.near_plane,
            value.far_plane,
            value.projection,
            value.orthographic_height,
        )

    @property
    def debug_line_count(self) -> int:
        return self._native.debug_line_count

    @property
    def gravity(self) -> Vec3:
        """Gravity for this scene's lazily-created native physics world."""

        return Vec3(self._native.physics_gravity())

    @gravity.setter
    def gravity(self, value: Vec3 | tuple[float, float, float]) -> None:
        gravity = Vec3.from_value(value)
        self._require_mutable()
        self._native.set_physics_gravity(tuple(gravity))

    @property
    def physics_step_count(self) -> int:
        return self._native.physics_step_count

    @property
    def entities(self) -> tuple[Entity, ...]:
        from .entity import Entity

        return tuple(Entity._from_handle(self, handle) for handle in self._native.entity_handles())

    def create_entity(self, name: str = "Entity") -> Entity:
        from .entity import Entity

        return Entity(name, scene=self)

    def destroy_entity(self, entity: Entity) -> None:
        from .entity import Entity

        if not isinstance(entity, Entity):
            raise TypeError("entity must be an easy3d.Entity")
        if entity.scene is not self:
            raise ValueError("entity belongs to a different scene")
        entity.destroy()

    def clear(self) -> None:
        """Destroy all entities while keeping the scene reusable."""

        self._require_mutable()
        if self._callback_mutation_allowed():
            self._deferred_clear = True
            self._deferred_destroy.clear()
        else:
            self._clear_now(None)

    def add_debug_line(
        self,
        start: Vec3 | tuple[float, float, float],
        end: Vec3 | tuple[float, float, float],
        *,
        color: ColorValue = (1, 1, 1, 1),
        depth_test: bool = True,
    ) -> None:
        if not isinstance(depth_test, bool):
            raise TypeError("depth_test must be a bool")
        start_value = Vec3.from_value(start)
        end_value = Vec3.from_value(end)
        self._require_mutable()
        self._native.add_debug_line(
            tuple(start_value),
            tuple(end_value),
            normalize_color(color),
            depth_test,
        )

    def clear_debug_lines(self) -> None:
        self._require_mutable()
        self._native.clear_debug_lines()

    def close(self) -> None:
        """Destroy all entities and permanently close this scene."""

        if self._closed:
            return
        if self._live_owner() is not None:
            raise RuntimeError("cannot close a scene while it is loaded by a Game")
        self._clear_now(None)
        self._native.active = False
        self._closed = True

    def _create_handle(self, name: str) -> EntityHandle:
        self._require_mutable()
        if not isinstance(name, str):
            raise TypeError("entity name must be a string")
        return self._native.create_entity(name)

    def _register_script_entity(self, entity: Entity) -> None:
        hooks = (
            "awake",
            "start",
            "fixed_update",
            "update",
            "late_update",
            "on_destroy",
            "on_collision_enter",
            "on_collision_stay",
            "on_collision_exit",
            "on_trigger_enter",
            "on_trigger_stay",
            "on_trigger_exit",
        )
        if any(callable(getattr(entity, hook, None)) for hook in hooks):
            self._script_entities[entity.id] = entity

    def _entity_for_handle(self, handle: EntityHandle) -> Entity:
        from .entity import Entity

        return self._script_entities.get(handle.id) or Entity._from_handle(self, handle)

    def _rollback_entity_construction(self, entity: Entity) -> None:
        """Remove a partially constructed entity without running lifecycle hooks."""

        if entity.is_alive:
            self._native.destroy_entity(entity._handle)
        self._script_entities.pop(entity.id, None)
        self._deferred_destroy.pop(entity.id, None)

    def _script_snapshot(self) -> tuple[Entity, ...]:
        return tuple(self._script_entities.values())

    def _destroy_entity(self, entity: Entity) -> None:
        self._require_mutable()
        if self._callback_mutation_allowed():
            self._deferred_destroy[entity.id] = entity
        else:
            self._destroy_now(entity, None)

    def _destroy_now(
        self,
        entity: Entity,
        on_destroy: Callable[[Entity], None] | None,
    ) -> None:
        if not entity.is_alive:
            self._native.destroy_entity(entity._handle)
            return
        try:
            if on_destroy is not None:
                on_destroy(entity)
            else:
                callback = getattr(entity, "on_destroy", None)
                if callable(callback):
                    callback()
        finally:
            self._native.destroy_entity(entity._handle)
            self._script_entities.pop(entity.id, None)
            owner = self._live_owner()
            if owner is not None:
                notify = getattr(owner, "_on_entity_destroyed", None)
                if callable(notify):
                    notify(entity)

    def _clear_now(self, on_destroy: Callable[[Entity], None] | None) -> None:
        entities = tuple(self._script_entities.values())
        first_error: BaseException | None = None
        for entity in entities:
            if not entity.is_alive:
                continue
            try:
                if on_destroy is not None:
                    on_destroy(entity)
                else:
                    callback = getattr(entity, "on_destroy", None)
                    if callable(callback):
                        callback()
            except BaseException as error:
                if first_error is None:
                    first_error = error
        self._native.clear()
        owner = self._live_owner()
        notify = None if owner is None else getattr(owner, "_on_entity_destroyed", None)
        if callable(notify):
            for entity in entities:
                notify(entity)
        self._script_entities.clear()
        self._deferred_destroy.clear()
        self._deferred_clear = False
        if first_error is not None:
            raise first_error

    def _commit_deferred(self, on_destroy: Callable[[Entity], None]) -> None:
        if self._deferred_clear:
            self._clear_now(on_destroy)
            return
        pending = tuple(self._deferred_destroy.values())
        self._deferred_destroy.clear()
        for entity in pending:
            if entity.is_alive:
                self._destroy_now(entity, on_destroy)

    def _attach(self, owner: object) -> None:
        self._require_open()
        current_owner = self._live_owner()
        if current_owner is not None and current_owner is not owner:
            raise RuntimeError("scene is already loaded by another Game")
        self._owner = weakref.ref(owner)
        self._native.active = True

    def _detach(self, owner: object) -> None:
        current_owner = self._live_owner()
        if current_owner is not None and current_owner is not owner:
            raise RuntimeError("scene is owned by another Game")
        self._owner = None
        self._native.active = False

    def _live_owner(self) -> object | None:
        return None if self._owner is None else self._owner()

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("scene is closed")

    def _require_mutable(self) -> None:
        self._require_open()
        owner = self._live_owner()
        if (owner is not None and bool(getattr(owner, "is_running", False)) and
                not self._callback_mutation_allowed()):
            raise RuntimeError(
                "cannot mutate a scene while its Game is running; "
                "mutations are allowed only from an active script callback"
            )

    def _callback_mutation_allowed(self) -> bool:
        owner = self._live_owner()
        check = None if owner is None else getattr(owner, "_allows_scene_mutation", None)
        return bool(check(self)) if callable(check) else False

    def __enter__(self) -> Scene:
        self._require_open()
        self._context_tokens.append(_current_scene.set(self))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._context_tokens:
            raise RuntimeError("scene context exit without matching enter")
        _current_scene.reset(self._context_tokens.pop())

    def __len__(self) -> int:
        return self.entity_count

    def __iter__(self) -> Iterator[Entity]:
        return iter(self.entities)

    def __repr__(self) -> str:
        return (
            f"Scene(name={self.name!r}, entities={self.entity_count}, "
            f"active={self.active}, closed={self.closed})"
        )
