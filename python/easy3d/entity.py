"""Python entity references backed by generation-checked native handles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._easy3d import EntityHandle

if TYPE_CHECKING:
    from .scene import Scene


class Entity:
    """A safe reference to an entity owned by exactly one :class:`Scene`.

    Entity data lives in the native scene registry. Destroying an entity or
    clearing its scene invalidates every wrapper that carries the old handle;
    subsequent property access raises :class:`easy3d.InvalidEntityError`.
    """

    def __init__(self, name: str = "Entity", *, scene: Scene | None = None) -> None:
        from .scene import Scene

        owner = scene if scene is not None else Scene.current()
        if not isinstance(owner, Scene):
            raise TypeError("scene must be an easy3d.Scene")
        self._scene = owner
        self._handle = owner._create_handle(name)

    @classmethod
    def _from_handle(cls, scene: Scene, handle: EntityHandle) -> Entity:
        entity = cls.__new__(cls)
        entity._scene = scene
        entity._handle = handle
        return entity

    @property
    def id(self) -> int:
        """Generation-qualified identifier unique within this entity's scene."""

        return self._handle.id

    @property
    def scene(self) -> Scene:
        return self._scene

    @property
    def is_alive(self) -> bool:
        return not self._scene.closed and self._scene._native.is_alive(self._handle)

    @property
    def name(self) -> str:
        return self._scene._native.entity_name(self._handle)

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("entity name must be a string")
        self._scene._native.set_entity_name(self._handle, value)

    @property
    def enabled(self) -> bool:
        return self._scene._native.entity_enabled(self._handle)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("enabled must be a bool")
        self._scene._native.set_entity_enabled(self._handle, value)

    @property
    def visible(self) -> bool:
        return self._scene._native.entity_visible(self._handle)

    @visible.setter
    def visible(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("visible must be a bool")
        self._scene._native.set_entity_visible(self._handle, value)

    def destroy(self) -> None:
        """Destroy this entity and invalidate all wrappers to its handle."""

        self._scene._native.destroy_entity(self._handle)

    def __repr__(self) -> str:
        if not self.is_alive:
            return f"Entity(id={self.id}, destroyed=True)"
        return f"Entity(name={self.name!r}, id={self.id})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self._scene is other._scene and self._handle == other._handle

    def __hash__(self) -> int:
        return hash((id(self._scene), self._handle.world_id, self.id))
