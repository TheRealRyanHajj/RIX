"""Typed, bounded input sequencing for the native character motor."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math

from ._easy3d import NetworkError
from .components import CharacterController
from .math import Quat, Vec3
from .replication import ClientReplication


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


@dataclass(frozen=True, slots=True)
class CharacterCorrection:
    """Authoritative post-input motor state; sequence zero is the initial state."""

    acknowledged_sequence: int
    server_tick: int
    position: tuple[float, float, float] | Vec3
    rotation: tuple[float, float, float, float] | Quat
    linear_velocity: tuple[float, float, float] | Vec3

    def __post_init__(self) -> None:
        sequence = self.acknowledged_sequence
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise TypeError("acknowledged_sequence must be an integer")
        if not 0 <= sequence <= _MAX_SEQUENCE:
            raise ValueError("acknowledged_sequence must be a uint64")
        if isinstance(self.server_tick, bool) or not isinstance(self.server_tick, int):
            raise TypeError("server_tick must be an integer")
        if not 0 <= self.server_tick <= _MAX_SEQUENCE:
            raise ValueError("server_tick must be a uint64")
        position = Vec3.from_value(self.position)
        rotation = (
            self.rotation if isinstance(self.rotation, Quat) else Quat(self.rotation)
        ).normalized()
        velocity = Vec3.from_value(self.linear_velocity)
        if velocity.length > 500.0:
            raise ValueError("linear_velocity must not exceed 500 m/s")
        object.__setattr__(self, "position", tuple(position))
        object.__setattr__(self, "rotation", tuple(rotation))
        object.__setattr__(self, "linear_velocity", tuple(velocity))


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    acknowledged_sequence: int
    server_tick: int
    replayed_inputs: int
    position_error: float


@dataclass(frozen=True, slots=True)
class CorrectionStats:
    corrections: int
    replayed_inputs: int
    last_replay_count: int
    last_position_error: float
    maximum_position_error: float
    total_position_error: float

    @property
    def average_position_error(self) -> float:
        return (
            self.total_position_error / self.corrections
            if self.corrections
            else 0.0
        )


@dataclass(frozen=True, slots=True)
class RemoteInterpolationStats:
    calls: int
    applied_objects: int
    last_authority_tick: float
    last_render_tick: float


class RemoteTransformInterpolator:
    """Apply the existing remote history at an explicit buffered render tick."""

    __slots__ = (
        "_replication",
        "_delay_ticks",
        "_calls",
        "_applied_objects",
        "_last_authority_tick",
        "_last_render_tick",
    )

    def __init__(
        self, replication: ClientReplication, *, delay_ticks: float = 2.0
    ) -> None:
        if not isinstance(replication, ClientReplication):
            raise TypeError("replication must be an easy3d.ClientReplication")
        delay = float(delay_ticks)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay_ticks must be finite and non-negative")
        self._replication = replication
        self._delay_ticks = delay
        self._calls = 0
        self._applied_objects = 0
        self._last_authority_tick = 0.0
        self._last_render_tick = 0.0

    @property
    def delay_ticks(self) -> float:
        return self._delay_ticks

    @property
    def stats(self) -> RemoteInterpolationStats:
        return RemoteInterpolationStats(
            self._calls,
            self._applied_objects,
            self._last_authority_tick,
            self._last_render_tick,
        )

    def update(self, authority_tick: float) -> int:
        if isinstance(authority_tick, bool) or not isinstance(
            authority_tick, (int, float)
        ):
            raise TypeError("authority_tick must be a number")
        tick = float(authority_tick)
        if not math.isfinite(tick) or not 0 <= tick <= _MAX_SEQUENCE:
            raise ValueError("authority_tick must be a finite non-negative uint64 range value")
        if self._calls and tick < self._last_authority_tick:
            raise ValueError("authority_tick cannot move backwards")
        render_tick = max(0.0, tick - self._delay_ticks)
        applied = self._replication.interpolate_transforms(render_tick)
        self._calls += 1
        self._applied_objects += applied
        self._last_authority_tick = tick
        self._last_render_tick = render_tick
        return applied


class PredictedCharacterController:
    """Apply sequenced inputs and retain a bounded client replay queue.

    Callers own transport. The authority snapshots post-step state and the
    client restores it before replaying the unacknowledged bounded suffix.
    """

    __slots__ = (
        "_controller",
        "_role",
        "_max_pending_inputs",
        "_pending",
        "_next_sequence",
        "_last_acknowledged_sequence",
        "_last_correction_tick",
        "_corrections",
        "_replayed_inputs",
        "_last_replay_count",
        "_last_position_error",
        "_maximum_position_error",
        "_total_position_error",
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
        self._last_correction_tick: int | None = None
        self._corrections = 0
        self._replayed_inputs = 0
        self._last_replay_count = 0
        self._last_position_error = 0.0
        self._maximum_position_error = 0.0
        self._total_position_error = 0.0

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

    @property
    def correction_stats(self) -> CorrectionStats:
        return CorrectionStats(
            self._corrections,
            self._replayed_inputs,
            self._last_replay_count,
            self._last_position_error,
            self._maximum_position_error,
            self._total_position_error,
        )

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

    def make_correction(self, server_tick: int) -> CharacterCorrection:
        """Snapshot authoritative state after its last accepted input was stepped."""

        self._require_role(PredictionRole.SERVER, "make_correction")
        if isinstance(server_tick, bool) or not isinstance(server_tick, int):
            raise TypeError("server_tick must be an integer")
        if not 0 <= server_tick <= _MAX_SEQUENCE:
            raise ValueError("server_tick must be a uint64")
        if (
            self._last_correction_tick is not None
            and server_tick <= self._last_correction_tick
        ):
            raise ValueError("server_tick must be strictly increasing")
        position, rotation, velocity, _ground_normal, _grounded = (
            self._controller._state()
        )
        correction = CharacterCorrection(
            self.last_input_sequence,
            server_tick,
            position,
            rotation,
            velocity,
        )
        self._last_correction_tick = server_tick
        return correction

    def reconcile(
        self,
        correction: CharacterCorrection,
        *,
        fixed_delta_seconds: float,
    ) -> ReconciliationResult:
        """Restore authority state and replay the bounded unacknowledged suffix."""

        self._require_role(PredictionRole.CLIENT, "reconcile")
        if not isinstance(correction, CharacterCorrection):
            raise TypeError("correction must be an easy3d.CharacterCorrection")
        delta = float(fixed_delta_seconds)
        if not math.isfinite(delta) or delta <= 0:
            raise ValueError("fixed_delta_seconds must be finite and positive")
        sequence = correction.acknowledged_sequence
        if sequence > self._next_sequence:
            raise ValueError("correction acknowledges an input that was not submitted")
        if sequence < self._last_acknowledged_sequence:
            raise ValueError("correction acknowledgement cannot move backwards")
        if (
            self._last_correction_tick is not None
            and correction.server_tick <= self._last_correction_tick
        ):
            raise ValueError("correction server_tick must be strictly increasing")

        current_position = self._controller.entity.position
        target_position = Vec3(correction.position)
        position_error = (current_position - target_position).length
        replay = tuple(
            command for command in self._pending if command.sequence > sequence
        )

        self._controller.correct_state(
            correction.position,
            correction.rotation,
            correction.linear_velocity,
        )
        for command in replay:
            self._controller.replay_input(
                command.movement,
                heading_degrees=command.heading_degrees,
                jump=command.jump,
                delta_seconds=delta,
            )

        self.acknowledge(sequence)
        self._last_correction_tick = correction.server_tick
        self._corrections += 1
        self._replayed_inputs += len(replay)
        self._last_replay_count = len(replay)
        self._last_position_error = position_error
        self._maximum_position_error = max(
            self._maximum_position_error, position_error
        )
        self._total_position_error += position_error
        return ReconciliationResult(
            sequence, correction.server_tick, len(replay), position_error
        )

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
