"""Server-authoritative replicated match phases and tick timers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .replication import (
    ClientReplication,
    NetworkObjectId,
    NetworkVar,
    NetworkValueType,
    PrefabId,
    PrefabRegistry,
    ServerReplication,
)


class MatchPhase(IntEnum):
    WAITING = 0
    COUNTDOWN = 1
    PLAYING = 2
    ROUND_END = 3
    MATCH_END = 4


@dataclass(frozen=True, slots=True)
class MatchStateFields:
    phase: int = 1
    round: int = 2
    deadline_tick: int = 3
    revision: int = 4

    def __post_init__(self) -> None:
        values = (self.phase, self.round, self.deadline_tick, self.revision)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("match-state field IDs must be integers")
        if any(not 1 <= value <= 65535 for value in values) or len(set(values)) != 4:
            raise ValueError("match-state field IDs must be unique nonzero uint16 values")


def register_match_state(
    registry: PrefabRegistry,
    prefab_id: PrefabId | int,
    *,
    fields: MatchStateFields = MatchStateFields(),
) -> MatchStateFields:
    """Add the canonical four-field match schema to a dedicated prefab."""

    if not isinstance(registry, PrefabRegistry):
        raise TypeError("registry must be a PrefabRegistry")
    if not isinstance(fields, MatchStateFields):
        raise TypeError("fields must be MatchStateFields")
    registry.register_variable(
        prefab_id, fields.phase, "match_phase", NetworkValueType.INT, int(MatchPhase.WAITING), max_bytes=8
    )
    registry.register_variable(
        prefab_id, fields.round, "match_round", NetworkValueType.INT, 0, max_bytes=8
    )
    registry.register_variable(
        prefab_id, fields.deadline_tick, "match_deadline_tick", NetworkValueType.INT, -1, max_bytes=8
    )
    registry.register_variable(
        prefab_id, fields.revision, "match_revision", NetworkValueType.INT, 0, max_bytes=8
    )
    return fields


def _tick(value: int, name: str = "tick") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= 2**63 - 1:
        raise ValueError(f"{name} must be in signed int64 tick range")
    return value


def _network_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"replicated {name} must be an integer")
    return value


class ClientMatchState:
    """Read-only view of one replicated match-state object."""

    __slots__ = ("_fields", "_object_id", "_replication")
    _replication: ClientReplication | ServerReplication

    def __init__(
        self,
        replication: ClientReplication,
        object_id: NetworkObjectId | int,
        *,
        fields: MatchStateFields = MatchStateFields(),
    ) -> None:
        if not isinstance(replication, ClientReplication):
            raise TypeError("replication must be ClientReplication")
        self._replication = replication
        self._object_id = object_id if isinstance(object_id, NetworkObjectId) else NetworkObjectId(object_id)
        self._fields = fields

    @property
    def phase(self) -> MatchPhase:
        return MatchPhase(
            _network_int(
                self._replication.variable(self._object_id, self._fields.phase).value,
                "match phase",
            )
        )

    @property
    def round(self) -> int:
        return _network_int(
            self._replication.variable(self._object_id, self._fields.round).value,
            "match round",
        )

    @property
    def deadline_tick(self) -> int | None:
        value = _network_int(
            self._replication.variable(self._object_id, self._fields.deadline_tick).value,
            "match deadline",
        )
        return None if value < 0 else value

    @property
    def revision(self) -> int:
        return _network_int(
            self._replication.variable(self._object_id, self._fields.revision).value,
            "match revision",
        )

    def remaining_ticks(self, tick: int) -> int:
        current = _tick(tick)
        deadline = self.deadline_tick
        return 0 if deadline is None else max(0, deadline - current)


class ServerMatchState(ClientMatchState):
    """Authority-only match transition state machine driven by simulation ticks."""

    __slots__ = ("_countdown_ticks", "_last_tick")
    _replication: ServerReplication

    def __init__(
        self,
        replication: ServerReplication,
        object_id: NetworkObjectId | int,
        *,
        fields: MatchStateFields = MatchStateFields(),
        countdown_ticks: int = 180,
    ) -> None:
        if not isinstance(replication, ServerReplication):
            raise TypeError("replication must be ServerReplication")
        self._replication = replication
        self._object_id = object_id if isinstance(object_id, NetworkObjectId) else NetworkObjectId(object_id)
        self._fields = fields
        self._countdown_ticks = _tick(countdown_ticks, "countdown_ticks")
        if self._countdown_ticks == 0:
            raise ValueError("countdown_ticks must be positive")
        self._last_tick = -1
        # Validate that all declared fields exist before gameplay begins.
        for field in (fields.phase, fields.round, fields.deadline_tick, fields.revision):
            replication.variable(self._object_id, field)

    def _variable(self, field: int) -> NetworkVar:
        return self._replication.variable(self._object_id, field)

    @property
    def phase(self) -> MatchPhase:
        return MatchPhase(
            _network_int(self._variable(self._fields.phase).value, "match phase")
        )

    @property
    def round(self) -> int:
        return _network_int(self._variable(self._fields.round).value, "match round")

    @property
    def deadline_tick(self) -> int | None:
        value = _network_int(
            self._variable(self._fields.deadline_tick).value, "match deadline"
        )
        return None if value < 0 else value

    @property
    def revision(self) -> int:
        return _network_int(
            self._variable(self._fields.revision).value, "match revision"
        )

    def _at(self, tick: int) -> int:
        value = _tick(tick)
        if value < self._last_tick:
            raise ValueError("match simulation tick cannot decrease")
        self._last_tick = value
        return value

    def _set(self, phase: MatchPhase, round_value: int, deadline: int | None) -> int:
        revision = self.revision
        if revision == 2**63 - 1:
            raise OverflowError("match revision space is exhausted")
        self._variable(self._fields.phase).value = int(phase)
        self._variable(self._fields.round).value = round_value
        self._variable(self._fields.deadline_tick).value = -1 if deadline is None else deadline
        self._variable(self._fields.revision).value = revision + 1
        return self._replication.flush()

    def start_match(self, tick: int, *, countdown_ticks: int | None = None) -> int:
        if self.phase not in (MatchPhase.WAITING, MatchPhase.MATCH_END):
            raise RuntimeError("match can start only while waiting or after match end")
        duration = self._countdown_ticks if countdown_ticks is None else _tick(countdown_ticks, "countdown_ticks")
        now = _tick(tick)
        if duration == 0 or now > 2**63 - 1 - duration:
            raise ValueError("countdown deadline is outside signed int64 tick range")
        self._at(now)
        return self._set(MatchPhase.COUNTDOWN, 1, now + duration)

    def finish_round(
        self,
        tick: int,
        *,
        intermission_ticks: int,
        match_over: bool = False,
    ) -> int:
        if self.phase is not MatchPhase.PLAYING:
            raise RuntimeError("a round can finish only while playing")
        if not isinstance(match_over, bool):
            raise TypeError("match_over must be bool")
        now = _tick(tick)
        if match_over:
            self._at(now)
            return self._set(MatchPhase.MATCH_END, self.round, None)
        duration = _tick(intermission_ticks, "intermission_ticks")
        if duration == 0 or now > 2**63 - 1 - duration:
            raise ValueError("intermission deadline is outside signed int64 tick range")
        self._at(now)
        return self._set(MatchPhase.ROUND_END, self.round, now + duration)

    def advance(self, tick: int) -> bool:
        now = self._at(tick)
        deadline = self.deadline_tick
        if deadline is None or now < deadline:
            return False
        if self.phase is MatchPhase.COUNTDOWN:
            self._set(MatchPhase.PLAYING, self.round, None)
            return True
        if self.phase is MatchPhase.ROUND_END:
            if self.round == 2**63 - 1:
                raise OverflowError("match round space is exhausted")
            if now > 2**63 - 1 - self._countdown_ticks:
                raise ValueError("next countdown deadline is outside signed int64 tick range")
            self._set(
                MatchPhase.COUNTDOWN,
                self.round + 1,
                now + self._countdown_ticks,
            )
            return True
        raise RuntimeError("only countdown and round-end phases may own deadlines")

    def reset(self, tick: int) -> int:
        if self.phase is not MatchPhase.MATCH_END:
            raise RuntimeError("match can reset only after match end")
        self._at(tick)
        return self._set(MatchPhase.WAITING, 0, None)


__all__ = [
    "ClientMatchState",
    "MatchPhase",
    "MatchStateFields",
    "ServerMatchState",
    "register_match_state",
]

