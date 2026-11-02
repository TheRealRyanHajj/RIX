"""Typed, bounded input sequencing for the native character motor."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math

from ._easy3d import NetworkError
from .components import CharacterController
from .math import Vec3


_MAX_SEQUENCE = (1 << 64) - 1


class PredictionRole(str, Enum):
    """Which side is driving a predicted character controller."""

    CLIENT = "client"
    SERVER = "server"


@dataclass(frozen=True, slots=True)
class CharacterInputCommand:
    """One immutable native character-motor input with a nonzero sequence."""

    sequence: int
    movement: tuple[float, float, float] | Vec3
    heading_degrees: float = 0.0
    jump: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise TypeError("sequence must be an integer")
        if self.sequence < 1 or self.sequence > _MAX_SEQUENCE:
            raise ValueError("sequence must be between 1 and 2^64 - 1")
        movement = Vec3.from_value(self.movement)
        heading = float(self.heading_degrees)
        if not math.isfinite(heading):
            raise ValueError("heading_degrees must be finite")
        if not isinstance(self.jump, bool):
            raise TypeError("jump must be a bool")
        object.__setattr__(self, "movement", tuple(movement))
        object.__setattr__(self, "heading_degrees", heading)


class PredictedCharacterController:
    """Apply sequenced inputs and retain a bounded client replay queue.

    This Phase 5.1 facade does not send commands or reconcile authoritative
    corrections. Callers own transport; Phase 5.2 consumes ``pending_inputs``
    for bounded replay.
    """

    __slots__ = (
        "_controller",
        "_role",
        "_max_pending_inputs",
        "_pending",
        "_next_sequence",
        "_last_acknowledged_sequence",
    )

    def __init__(
        self,
        controller: CharacterController,
        *,
        role: PredictionRole | str,
        max_pending_inputs: int = 256,
    ) -> None:
        if not isinstance(controller, CharacterController):
            raise TypeError("controller must be an easy3d.CharacterController")
        try:
            parsed_role = PredictionRole(role)
        except (TypeError, ValueError) as error:
            raise ValueError("role must be 'client' or 'server'") from error
        if (
            isinstance(max_pending_inputs, bool)
            or not isinstance(max_pending_inputs, int)
            or max_pending_inputs < 1
        ):
            raise ValueError("max_pending_inputs must be a positive integer")
        self._controller = controller
        self._role = parsed_role
        self._max_pending_inputs = max_pending_inputs
        self._pending: deque[CharacterInputCommand] = deque()
        self._next_sequence = controller.last_input_sequence
        self._last_acknowledged_sequence = 0

    @property
    def controller(self) -> CharacterController:
        return self._controller

    @property
    def role(self) -> PredictionRole:
        return self._role

    @property
    def max_pending_inputs(self) -> int:
        return self._max_pending_inputs

    @property
    def last_input_sequence(self) -> int:
        return self._controller.last_input_sequence

    @property
    def last_acknowledged_sequence(self) -> int:
        return self._last_acknowledged_sequence

    @property
    def pending_inputs(self) -> tuple[CharacterInputCommand, ...]:
        return tuple(self._pending)

    def submit(
        self,
        movement: Vec3 | tuple[float, float, float],
        *,
        heading_degrees: float = 0.0,
        jump: bool = False,
    ) -> CharacterInputCommand:
        """Allocate and immediately apply one client input."""

        self._require_role(PredictionRole.CLIENT, "submit")
        if len(self._pending) >= self._max_pending_inputs:
            raise NetworkError("predicted input queue is full")
        if self._next_sequence >= _MAX_SEQUENCE:
            raise NetworkError("character input sequence is exhausted")
        command = CharacterInputCommand(
            self._next_sequence + 1, movement, heading_degrees, jump
        )
        self._apply(command)
        self._next_sequence = command.sequence
        self._pending.append(command)
        return command

    def accept(self, command: CharacterInputCommand) -> None:
        """Validate and apply one externally sequenced server input."""

        self._require_role(PredictionRole.SERVER, "accept")
        if not isinstance(command, CharacterInputCommand):
            raise TypeError("command must be an easy3d.CharacterInputCommand")
        self._apply(command)
        self._next_sequence = command.sequence

    def acknowledge(self, sequence: int) -> int:
        """Remove acknowledged client inputs and return the removal count."""

        self._require_role(PredictionRole.CLIENT, "acknowledge")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise TypeError("sequence must be an integer")
        if sequence < self._last_acknowledged_sequence:
            raise ValueError("acknowledgement sequence cannot move backwards")
        if sequence > self._next_sequence:
            raise ValueError("cannot acknowledge an input that was not submitted")
        removed = 0
        while self._pending and self._pending[0].sequence <= sequence:
            self._pending.popleft()
            removed += 1
        self._last_acknowledged_sequence = sequence
        return removed

    def _apply(self, command: CharacterInputCommand) -> None:
        self._controller.set_sequenced_input(
            command.sequence,
            command.movement,
            heading_degrees=command.heading_degrees,
            jump=command.jump,
        )

    def _require_role(self, expected: PredictionRole, operation: str) -> None:
        if self._role is not expected:
            raise NetworkError(f"{operation} is only valid for the {expected.value} role")
