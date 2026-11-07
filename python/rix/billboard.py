"""Camera-facing 3D quads backed by ordinary Pygame images."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

from .math import Vec3
from .primitives import Plane
from .textures import SurfaceTexture

if TYPE_CHECKING:
    from .scene import Scene
    from .world import World


class Billboard(Plane):
    """A textured world-space quad that tracks the active camera."""

    def __init__(
        self,
        world: World | None = None,
        *,
        image: object | SurfaceTexture,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        scale: float = 1.0,
        axis: Literal["free", "y"] = "free",
        rotation: float = 0.0,
        collider: bool = True,
        name: str = "Billboard",
        scene: Scene | None = None,
    ) -> None:
        size = float(scale)
        if not math.isfinite(size) or size <= 0:
            raise ValueError("billboard scale must be finite and positive")
        if axis not in ("free", "y"):
            raise ValueError("billboard axis must be 'free' or 'y'")
        spin = float(rotation)
        if not math.isfinite(spin):
            raise ValueError("billboard rotation must be finite")
        texture = image if isinstance(image, SurfaceTexture) else SurfaceTexture(image)
        aspect = texture.width / texture.height
        self._billboard_axis = axis
        self._billboard_spin = spin
        super().__init__(
            world,
            position=position,
            rotation=(90.0, 0.0, spin),
            size=(size * aspect, size),
            texture=texture,
            double_sided=True,
            collider=collider,
            name=name,
            scene=scene,
        )
        self.update = self._face_camera  # type: ignore[method-assign]
        self.scene._register_script_entity(self)
        self._face_camera(0.0)

    @property
    def image(self) -> SurfaceTexture:
        return self.texture  # type: ignore[no-any-return,attr-defined]

    def _face_camera(self, _dt: float) -> None:
        camera = self.scene.camera
        delta = camera.position - self.world_position
        horizontal = math.hypot(delta.x, delta.z)
        if horizontal <= 1.0e-12 and abs(delta.y) <= 1.0e-12:
            return
        yaw = math.degrees(math.atan2(delta.x, delta.z))
        pitch = 0.0 if self._billboard_axis == "y" else math.degrees(
            math.atan2(delta.y, horizontal)
        )
        self.rotation = (90.0 - pitch, yaw, self._billboard_spin)

