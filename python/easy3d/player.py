"""Convenience player entity backed by the native character motor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import CharacterController, CharacterMode
from .entity import Entity
from .math import Vec3

if TYPE_CHECKING:
    from .scene import Scene


class Player(Entity):
    """An entity with a configured first- or third-person character controller."""

    def __init__(
        self,
        *,
        position: Vec3 | tuple[float, float, float] = (0, 0, 0),
        controller: CharacterMode = "first_person",
        radius: float = 0.4,
        height: float = 1.8,
        speed: float = 5.0,
        acceleration: float = 30.0,
        air_control: float = 0.25,
        jump_speed: float = 5.0,
        max_slope_degrees: float = 50.0,
        step_height: float = 0.4,
        name: str = "Player",
        scene: Scene | None = None,
    ) -> None:
        super().__init__(name, scene=scene)
        try:
            self.position = position
            self.add_component(
                CharacterController,
                mode=controller,
                radius=radius,
                height=height,
                speed=speed,
                acceleration=acceleration,
                air_control=air_control,
                jump_speed=jump_speed,
                max_slope_degrees=max_slope_degrees,
                step_height=step_height,
            )
        except Exception:
            self.scene._rollback_entity_construction(self)
            raise

    @property
    def controller(self) -> CharacterController:
        result = self.get_component(CharacterController)
        if result is None:
            raise RuntimeError("player character controller was removed")
        return result

    def move(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
    ) -> None:
        self.controller.set_input(
            movement, heading_degrees=heading_degrees, jump=jump
        )
