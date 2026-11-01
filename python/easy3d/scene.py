"""Scene ownership and context-managed entity construction."""

from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar, Token
from types import TracebackType
from typing import TYPE_CHECKING
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
        self._native.clear()

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
        self._native.clear()
        self._native.active = False
        self._closed = True

    def _create_handle(self, name: str) -> EntityHandle:
        self._require_mutable()
        if not isinstance(name, str):
            raise TypeError("entity name must be a string")
        return self._native.create_entity(name)

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
        if owner is not None and bool(getattr(owner, "is_running", False)):
            raise RuntimeError(
                "cannot mutate a scene while its Game is running; "
                "runtime scheduling arrives in Phase 2"
            )

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
