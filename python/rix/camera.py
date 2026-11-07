"""Typed public camera configuration and matrix queries."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal, TypeAlias

from ._rix import (
    _camera_aspect_ratio,
    _camera_look_at,
    _camera_projection_matrix,
    _camera_view_matrix,
)
from .math import Quat, Vec3, _finite

Matrix4 = tuple[
    float, float, float, float,
    float, float, float, float,
    float, float, float, float,
    float, float, float, float,
]
Projection: TypeAlias = Literal["perspective", "orthographic"]


class Camera:
    """Perspective or orthographic right-handed, -Z-forward camera value."""

    __slots__ = (
        "_position",
        "_rotation",
        "_vertical_fov_degrees",
        "_near_plane",
        "_far_plane",
        "_projection",
        "_orthographic_height",
        "_on_change",
    )

    def __init__(
        self,
        *,
        position: Vec3 | Iterable[float] = (0.0, 0.0, 0.0),
        rotation: Vec3 | Iterable[float] = (0.0, 0.0, 0.0),
        vertical_fov_degrees: float = 60.0,
        near_plane: float = 0.1,
        far_plane: float = 1000.0,
        projection: Projection = "perspective",
        orthographic_height: float = 10.0,
        _on_change: Callable[[Camera], None] | None = None,
    ) -> None:
        self._on_change: Callable[[Camera], None] | None = None
        self._position = Vec3.from_value(position)
        self._rotation = Vec3.from_value(rotation)
        self._vertical_fov_degrees = 70.0
        self._near_plane = 0.1
        self._far_plane = 1000.0
        self._projection: Projection = "perspective"
        self._orthographic_height = 10.0
        self.vertical_fov_degrees = vertical_fov_degrees
        self.near_plane = near_plane
        self.far_plane = far_plane
        self.projection = projection
        self.orthographic_height = orthographic_height
        self._on_change = _on_change

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change(self)

    def _bind(self, callback: Callable[[Camera], None] | None) -> None:
        self._on_change = callback

    @property
    def position(self) -> Vec3:
        return self._position

    @position.setter
    def position(self, value: Vec3 | Iterable[float]) -> None:
        self._position = Vec3.from_value(value)
        self._changed()

    @property
    def rotation(self) -> Vec3:
        """Euler rotation in degrees."""

        return self._rotation

    @rotation.setter
    def rotation(self, value: Vec3 | Iterable[float]) -> None:
        self._rotation = Vec3.from_value(value)
        self._changed()

    @property
    def vertical_fov_degrees(self) -> float:
        return self._vertical_fov_degrees

    @vertical_fov_degrees.setter
    def vertical_fov_degrees(self, value: float) -> None:
        result = _finite(value, "vertical_fov_degrees")
        if result <= 0.0 or result >= 180.0:
            raise ValueError("vertical_fov_degrees must be between 0 and 180")
        self._vertical_fov_degrees = result
        self._changed()

    @property
    def near_plane(self) -> float:
        return self._near_plane

    @near_plane.setter
    def near_plane(self, value: float) -> None:
        result = _finite(value, "near_plane")
        if result <= 0.0:
            raise ValueError("near_plane must be positive")
        if result >= self._far_plane:
            raise ValueError("near_plane must be less than far_plane")
        self._near_plane = result
        self._changed()

    @property
    def far_plane(self) -> float:
        return self._far_plane

    @far_plane.setter
    def far_plane(self, value: float) -> None:
        result = _finite(value, "far_plane")
        if result <= self._near_plane:
            raise ValueError("far_plane must be greater than near_plane")
        self._far_plane = result
        self._changed()

    @property
    def projection(self) -> Projection:
        return self._projection

    @projection.setter
    def projection(self, value: Projection) -> None:
        if value not in ("perspective", "orthographic"):
            raise ValueError("projection must be 'perspective' or 'orthographic'")
        self._projection = value
        self._changed()

    @property
    def orthographic_height(self) -> float:
        return self._orthographic_height

    @orthographic_height.setter
    def orthographic_height(self, value: float) -> None:
        result = _finite(value, "orthographic_height")
        if result <= 0.0:
            raise ValueError("orthographic_height must be positive")
        self._orthographic_height = result
        self._changed()

    @property
    def quaternion(self) -> Quat:
        return Quat.from_euler(self._rotation)

    @property
    def forward(self) -> Vec3:
        return self.quaternion.rotate(Vec3(0.0, 0.0, -1.0))

    @property
    def right(self) -> Vec3:
        return self.quaternion.rotate(Vec3(1.0, 0.0, 0.0))

    @property
    def up(self) -> Vec3:
        return self.quaternion.rotate(Vec3(0.0, 1.0, 0.0))

    @staticmethod
    def aspect_ratio(resolution: tuple[int, int]) -> float:
        width, height = _resolution(resolution)
        return float(_camera_aspect_ratio(width, height))

    def view_matrix(self) -> Matrix4:
        quaternion = self.quaternion
        return _camera_view_matrix(
            self.position.x,
            self.position.y,
            self.position.z,
            quaternion.w,
            quaternion.x,
            quaternion.y,
            quaternion.z,
        )

    def projection_matrix(
        self,
        resolution: tuple[int, int],
        *,
        homogeneous_depth: bool = False,
    ) -> Matrix4:
        return _camera_projection_matrix(
            self.vertical_fov_degrees,
            self.near_plane,
            self.far_plane,
            self.projection == "orthographic",
            self.orthographic_height,
            self.aspect_ratio(resolution),
            homogeneous_depth,
        )

    def look_at(
        self,
        target: Vec3 | Iterable[float],
        *,
        up: Vec3 | Iterable[float] = (0.0, 1.0, 0.0),
    ) -> Camera:
        target_value = Vec3.from_value(target)
        up_value = Vec3.from_value(up)
        quaternion = Quat(
            *_camera_look_at(
                self.position.x,
                self.position.y,
                self.position.z,
                target_value.x,
                target_value.y,
                target_value.z,
                up_value.x,
                up_value.y,
                up_value.z,
            )
        )
        self.rotation = quaternion.to_euler()
        return self

    def __repr__(self) -> str:
        return (
            f"Camera(position={self.position!r}, rotation={self.rotation!r}, "
            f"vertical_fov_degrees={self.vertical_fov_degrees!r}, "
            f"near_plane={self.near_plane!r}, far_plane={self.far_plane!r}, "
            f"projection={self.projection!r}, "
            f"orthographic_height={self.orthographic_height!r})"
        )


def _resolution(value: object) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError("resolution must be a (width, height) tuple")
    width, height = value
    if isinstance(width, bool) or not isinstance(width, int):
        raise TypeError("resolution width must be an integer")
    if isinstance(height, bool) or not isinstance(height, int):
        raise TypeError("resolution height must be an integer")
    if width <= 0 or height <= 0:
        raise ValueError("resolution width and height must be positive")
    return width, height
