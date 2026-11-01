"""Python entity references backed by generation-checked native handles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from ._easy3d import EntityHandle
from .math import Quat, Vec3

if TYPE_CHECKING:
    from .scene import Scene

_ComponentT = TypeVar("_ComponentT")


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
        owner._register_script_entity(self)

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
        self._scene._require_mutable()
        self._scene._native.set_entity_name(self._handle, value)

    @property
    def enabled(self) -> bool:
        return self._scene._native.entity_enabled(self._handle)

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("enabled must be a bool")
        self._scene._require_mutable()
        self._scene._native.set_entity_enabled(self._handle, value)

    @property
    def visible(self) -> bool:
        return self._scene._native.entity_visible(self._handle)

    @visible.setter
    def visible(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("visible must be a bool")
        self._scene._require_mutable()
        self._scene._native.set_entity_visible(self._handle, value)

    @property
    def position(self) -> Vec3:
        """Live local-space position. Component assignment persists natively."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_local_position(self._handle)),
            self._set_position,
        )

    @position.setter
    def position(self, value: Vec3 | tuple[float, float, float]) -> None:
        vector = Vec3.from_value(value)
        self._scene._require_mutable()
        self._scene._native.set_entity_local_position(self._handle, *vector)

    def _set_position(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_local_position(self._handle, *value)

    @property
    def rotation(self) -> Vec3:
        """Live local Euler rotation in degrees (internally a quaternion)."""

        def get_euler() -> tuple[float, float, float]:
            return tuple(Quat(self._scene._native.entity_local_rotation(self._handle)).to_euler())

        def set_euler(value: tuple[float, float, float]) -> None:
            self._scene._require_mutable()
            self._scene._native.set_entity_local_rotation(
                self._handle, *Quat.from_euler(value)
            )

        return Vec3._live(get_euler, set_euler)

    @rotation.setter
    def rotation(self, value: Vec3 | tuple[float, float, float]) -> None:
        self.quaternion = Quat.from_euler(value)

    @property
    def quaternion(self) -> Quat:
        return Quat(self._scene._native.entity_local_rotation(self._handle))

    @quaternion.setter
    def quaternion(self, value: Quat) -> None:
        if not isinstance(value, Quat):
            raise TypeError("quaternion must be an easy3d.Quat")
        self._scene._require_mutable()
        self._scene._native.set_entity_local_rotation(self._handle, *value)

    @property
    def scale(self) -> Vec3:
        """Live local-space scale. Scale components must remain nonzero."""

        return Vec3._live(
            lambda: tuple(self._scene._native.entity_local_scale(self._handle)),
            self._set_scale,
        )

    @scale.setter
    def scale(self, value: Vec3 | tuple[float, float, float]) -> None:
        vector = Vec3.from_value(value)
        self._scene._require_mutable()
        self._scene._native.set_entity_local_scale(self._handle, *vector)

    def _set_scale(self, value: tuple[float, float, float]) -> None:
        self._scene._require_mutable()
        self._scene._native.set_entity_local_scale(self._handle, *value)

    def _world_components(self) -> tuple[tuple[float, float, float], tuple[float, float, float, float], tuple[float, float, float]]:
        position, rotation, scale = self._scene._native.entity_world_transform(self._handle)
        return tuple(position), tuple(rotation), tuple(scale)

    @property
    def world_position(self) -> Vec3:
        return Vec3(self._world_components()[0])

    @property
    def world_quaternion(self) -> Quat:
        return Quat(self._world_components()[1])

    @property
    def world_rotation(self) -> Vec3:
        return self.world_quaternion.to_euler()

    @property
    def world_scale(self) -> Vec3:
        return Vec3(self._world_components()[2])

    @property
    def parent(self) -> Entity | None:
        handle = self._scene._native.entity_parent(self._handle)
        return None if handle is None else Entity._from_handle(self._scene, handle)

    @parent.setter
    def parent(self, value: Entity | None) -> None:
        self.set_parent(value)

    @property
    def children(self) -> tuple[Entity, ...]:
        return tuple(
            Entity._from_handle(self._scene, handle)
            for handle in self._scene._native.entity_children(self._handle)
        )

    def set_parent(self, parent: Entity | None, *, keep_world: bool = False) -> None:
        if parent is not None and not isinstance(parent, Entity):
            raise TypeError("parent must be an easy3d.Entity or None")
        if parent is not None and parent.scene is not self._scene:
            raise ValueError("parent belongs to a different scene")
        self._scene._require_mutable()
        self._scene._native.set_entity_parent(
            self._handle,
            None if parent is None else parent._handle,
            bool(keep_world),
        )

    def destroy(self) -> None:
        """Destroy this entity and invalidate all wrappers to its handle."""

        self._scene._destroy_entity(self)

    def add_component(
        self, component_type: type[_ComponentT], **kwargs: Any
    ) -> _ComponentT:
        """Attach a supported singleton component and return its live facade."""

        from .components import Collider, Rigidbody

        if component_type is Collider:
            return cast(_ComponentT, Collider(self, **kwargs))
        if component_type is Rigidbody:
            return cast(_ComponentT, Rigidbody(self, **kwargs))
        raise TypeError("unsupported component type for add_component")

    def has_component(self, component_type: type[_ComponentT]) -> bool:
        from .components import Collider, LightComponent, MeshRenderer, Rigidbody

        if component_type is MeshRenderer:
            return self._scene._native.has_render_component(self._handle)
        if component_type is LightComponent:
            return self._scene._native.has_light_component(self._handle)
        if component_type is Collider:
            return self._scene._native.has_collider_component(self._handle)
        if component_type is Rigidbody:
            return self._scene._native.has_rigid_body_component(self._handle)
        raise TypeError("unsupported component type")

    def get_component(self, component_type: type[_ComponentT]) -> _ComponentT | None:
        from .components import Collider, LightComponent, MeshRenderer, Rigidbody

        if component_type is MeshRenderer:
            return (
                cast(_ComponentT, MeshRenderer(self))
                if self.has_component(MeshRenderer)
                else None
            )
        if component_type is LightComponent:
            return (
                cast(_ComponentT, LightComponent(self))
                if self.has_component(LightComponent)
                else None
            )
        if component_type is Collider:
            return (
                cast(_ComponentT, Collider._existing(self))
                if self.has_component(Collider)
                else None
            )
        if component_type is Rigidbody:
            return (
                cast(_ComponentT, Rigidbody._existing(self))
                if self.has_component(Rigidbody)
                else None
            )
        raise TypeError("unsupported component type")

    def remove_component(self, component_type: type[_ComponentT]) -> None:
        component = self.get_component(component_type)
        if component is None:
            raise ValueError("entity does not have the requested component")
        cast(Any, component).remove()

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
