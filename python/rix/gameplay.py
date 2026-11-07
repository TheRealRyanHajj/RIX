"""Composable high-level gameplay helpers over RIX production systems."""

from __future__ import annotations

import math
import random
import weakref
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from .entity import Entity
from .components import CollisionLayer, ColorValue, normalize_color
from .math import Quat, Vec3
from .physics import PhysicsHit, raycast
from .player import Player
from .primitives import Cube
from .utilities import Cooldown, EventBus, Subscription

if TYPE_CHECKING:
    from .game import CallbackHandle, Game


def _positive(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _non_negative(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


@dataclass(frozen=True, slots=True)
class DamageEvent:
    target: Entity
    amount: float
    previous: float
    current: float
    source: Entity | None = None


@dataclass(frozen=True, slots=True)
class DeathEvent:
    target: Entity
    source: Entity | None = None


_health_registry: weakref.WeakValueDictionary[tuple[int, int], Health] = (
    weakref.WeakValueDictionary()
)


class Health:
    """Mutable health attached to one entity with ordered damage/death events."""

    def __init__(
        self,
        entity: Entity,
        maximum: float = 100,
        *,
        current: float | None = None,
        invulnerable: bool = False,
    ) -> None:
        if not isinstance(entity, Entity):
            raise TypeError("entity must be an rix.Entity")
        if not isinstance(invulnerable, bool):
            raise TypeError("invulnerable must be a bool")
        self.entity = entity
        self.maximum = _positive(maximum, "maximum health")
        self._current = self.maximum if current is None else float(current)
        if not math.isfinite(self._current) or not 0 <= self._current <= self.maximum:
            raise ValueError("current health must be finite and between zero and maximum")
        self.invulnerable = invulnerable
        self.events = EventBus()
        key = (entity.scene.world_id, entity.id)
        existing = _health_registry.get(key)
        if existing is not None:
            raise ValueError("entity already has Health")
        _health_registry[key] = self
        entity.health = self  # type: ignore[attr-defined]

    @classmethod
    def for_entity(cls, entity: Entity) -> Health | None:
        if not isinstance(entity, Entity):
            raise TypeError("entity must be an rix.Entity")
        return _health_registry.get((entity.scene.world_id, entity.id))

    @property
    def current(self) -> float:
        return self._current

    @property
    def alive(self) -> bool:
        return self._current > 0

    @property
    def fraction(self) -> float:
        return self._current / self.maximum

    def on_damage(self, callback: Callable[[DamageEvent], None]) -> Subscription:
        return self.events.subscribe("damage", callback)

    def on_death(self, callback: Callable[[DeathEvent], None]) -> Subscription:
        return self.events.subscribe("death", callback)

    def on_change(self, callback: Callable[[Health], None]) -> Subscription:
        return self.events.subscribe("change", callback)

    def damage(self, amount: float, *, source: Entity | None = None) -> DamageEvent | None:
        value = _non_negative(amount, "damage")
        if value == 0 or self.invulnerable or not self.alive:
            return None
        previous = self._current
        self._current = max(0.0, previous - value)
        event = DamageEvent(self.entity, previous - self._current, previous, self._current, source)
        self.events.emit("damage", event)
        self.events.emit("change", self)
        if not self.alive:
            self.events.emit("death", DeathEvent(self.entity, source))
        return event

    def heal(self, amount: float) -> float:
        value = _non_negative(amount, "healing")
        previous = self._current
        self._current = min(self.maximum, previous + value)
        if self._current != previous:
            self.events.emit("change", self)
        return self._current - previous

    def reset(self, value: float | None = None) -> None:
        target = self.maximum if value is None else float(value)
        if not math.isfinite(target) or not 0 <= target <= self.maximum:
            raise ValueError("reset health must be between zero and maximum")
        self._current = target
        self.events.emit("change", self)


@dataclass(frozen=True, slots=True)
class SpawnPoint:
    position: Vec3
    rotation: Vec3 = field(default_factory=Vec3)
    team: str | None = None
    name: str = "Spawn"

    def __init__(
        self,
        position: Vec3 | tuple[float, float, float],
        rotation: Vec3 | tuple[float, float, float] = (0, 0, 0),
        *,
        team: str | None = None,
        name: str = "Spawn",
    ) -> None:
        if team is not None and (not isinstance(team, str) or not team):
            raise ValueError("team must be a non-empty string or None")
        if not isinstance(name, str) or not name:
            raise ValueError("spawn name must be a non-empty string")
        object.__setattr__(self, "position", Vec3.from_value(position))
        object.__setattr__(self, "rotation", Vec3.from_value(rotation))
        object.__setattr__(self, "team", team)
        object.__setattr__(self, "name", name)


class Respawner:
    """Select spawn points and reset native transforms plus optional Health."""

    def __init__(self, points: Iterable[SpawnPoint], *, seed: int = 0) -> None:
        self.points = tuple(points)
        if not self.points or not all(isinstance(point, SpawnPoint) for point in self.points):
            raise ValueError("Respawner requires at least one SpawnPoint")
        self._random = random.Random(seed)

    def choose(self, *, team: str | None = None) -> SpawnPoint:
        choices = tuple(point for point in self.points if team is None or point.team in (None, team))
        if not choices:
            raise LookupError(f"no spawn point is available for team {team!r}")
        return self._random.choice(choices)

    def respawn(
        self,
        entity: Entity,
        *,
        health: Health | None = None,
        team: str | None = None,
        point: SpawnPoint | None = None,
    ) -> SpawnPoint:
        destination = self.choose(team=team) if point is None else point
        entity.teleport(destination.position, destination.rotation)
        target_health = Health.for_entity(entity) if health is None else health
        if target_health is not None:
            target_health.reset()
        entity.show().enable()
        return destination


class Scoreboard:
    """Named integer scores with deterministic descending ranking."""

    def __init__(self) -> None:
        self._scores: dict[str, int] = {}
        self.events = EventBus()

    def on_change(self, callback: Callable[[Scoreboard], None]) -> Subscription:
        return self.events.subscribe("change", callback)

    def add_player(self, name: str, *, score: int = 0) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("player name must be a non-empty string")
        if name in self._scores:
            raise ValueError(f"score entry {name!r} already exists")
        self._scores[name] = int(score)
        self.events.emit("change", self)

    def remove_player(self, name: str) -> None:
        if self._scores.pop(name, None) is not None:
            self.events.emit("change", self)

    def add(self, name: str, points: int = 1) -> int:
        if name not in self._scores:
            raise KeyError(f"unknown score entry {name!r}")
        self._scores[name] += int(points)
        self.events.emit("change", self)
        return self._scores[name]

    def score(self, name: str) -> int:
        return self._scores[name]

    @property
    def ranking(self) -> tuple[tuple[str, int], ...]:
        return tuple(sorted(self._scores.items(), key=lambda item: (-item[1], item[0])))


@dataclass(frozen=True, slots=True)
class Team:
    """Named team with a normalized display color."""

    name: str
    color: tuple[float, float, float, float]

    def __init__(self, name: str, color: ColorValue = "white") -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("team name must be a non-empty string")
        object.__setattr__(self, "name", name.strip())
        object.__setattr__(self, "color", normalize_color(color))


class TeamRoster:
    """Explicit entity-to-team assignments without imposing game rules."""

    def __init__(self, *teams: Team) -> None:
        if not teams or not all(isinstance(team, Team) for team in teams):
            raise ValueError("TeamRoster requires at least one Team")
        if len({team.name for team in teams}) != len(teams):
            raise ValueError("team names must be unique")
        self.teams = tuple(teams)
        self._by_name = {team.name: team for team in teams}
        self._assignments: dict[tuple[int, int], tuple[Entity, Team]] = {}
        self.events = EventBus()

    def assign(self, entity: Entity, team: Team | str) -> Team:
        if not isinstance(entity, Entity):
            raise TypeError("entity must be an rix.Entity")
        selected = self._by_name[team] if isinstance(team, str) else team
        if selected.name not in self._by_name or self._by_name[selected.name] != selected:
            raise ValueError("team does not belong to this roster")
        self._assignments[(entity.scene.world_id, entity.id)] = (entity, selected)
        self.events.emit("change", self, entity, selected)
        return selected

    def remove(self, entity: Entity) -> bool:
        removed = self._assignments.pop((entity.scene.world_id, entity.id), None)
        if removed is not None:
            self.events.emit("change", self, entity, None)
        return removed is not None

    def team_of(self, entity: Entity) -> Team | None:
        assigned = self._assignments.get((entity.scene.world_id, entity.id))
        return None if assigned is None else assigned[1]

    def members(self, team: Team | str) -> tuple[Entity, ...]:
        selected = self._by_name[team] if isinstance(team, str) else team
        return tuple(
            entity
            for entity, assigned in self._assignments.values()
            if assigned == selected and entity.is_alive
        )

    def smallest(self) -> Team:
        """Return the least populated team, using declaration order for ties."""

        return min(self.teams, key=lambda team: len(self.members(team)))


@dataclass(frozen=True, slots=True)
class ShotResult:
    hit: PhysicsHit | None
    damage: DamageEvent | None


class HitscanWeapon:
    """Simulation-time weapon using the native collision-aware raycast path."""

    def __init__(
        self,
        owner: Entity,
        *,
        damage: float = 25,
        range: float = 50,
        cooldown: float = 0.2,
    ) -> None:
        if not isinstance(owner, Entity):
            raise TypeError("owner must be an rix.Entity")
        self.owner = owner
        self.damage = _positive(damage, "weapon damage")
        self.range = _positive(range, "weapon range")
        self.cooldown = Cooldown(_positive(cooldown, "weapon cooldown"))
        self._managed_handle: CallbackHandle | None = None
        self._aim: Callable[[], tuple[Vec3, Vec3]] | None = None

    @property
    def ready(self) -> bool:
        return self.cooldown.ready

    def advance(self, delta_seconds: float) -> None:
        self.cooldown.advance(delta_seconds)

    @property
    def managed(self) -> bool:
        return self._managed_handle is not None and self._managed_handle.active

    def _manage(
        self,
        game: Game,
        *,
        aim: Callable[[], tuple[Vec3, Vec3]] | None = None,
    ) -> CallbackHandle:
        if self.managed:
            raise ValueError("weapon is already managed")
        self._aim = aim
        self._managed_handle = game.subscribe_update(self.advance)
        return self._managed_handle

    def close(self) -> None:
        if self._managed_handle is not None:
            self._managed_handle.cancel()
            self._managed_handle = None

    def fire(
        self,
        origin: Vec3 | tuple[float, float, float] | None = None,
        direction: Vec3 | tuple[float, float, float] | None = None,
        *,
        layers: Iterable[CollisionLayer] | None = None,
        include_triggers: bool = False,
        exclude: Entity | None = None,
    ) -> ShotResult | None:
        if not self.cooldown.trigger():
            return None
        managed_origin: Vec3 | None = None
        managed_direction: Vec3 | None = None
        if origin is None and direction is None and self._aim is not None:
            managed_origin, managed_direction = self._aim()
        start = (
            managed_origin or self.owner.world_position
            if origin is None
            else Vec3.from_value(origin)
        )
        aim = (
            managed_direction or self.owner.world_quaternion.rotate((0, 0, -1))
            if direction is None
            else Vec3.from_value(direction)
        )
        hit = raycast(
            self.owner.scene,
            start,
            aim,
            self.range,
            layers=layers,
            include_triggers=include_triggers,
            exclude=self.owner if exclude is None else exclude,
        )
        damage_event = None
        if hit is not None:
            target_health = Health.for_entity(hit.entity)
            if target_health is not None:
                damage_event = target_health.damage(self.damage, source=self.owner)
        return ShotResult(hit, damage_event)


class Interaction:
    """Distance-validated interaction callback."""

    def __init__(
        self,
        entity: Entity,
        callback: Callable[[Entity], None],
        *,
        distance: float = 2.5,
    ) -> None:
        if not isinstance(entity, Entity):
            raise TypeError("entity must be an rix.Entity")
        if not callable(callback):
            raise TypeError("interaction callback must be callable")
        self.entity = entity
        self.callback = callback
        self.distance = _positive(distance, "interaction distance")

    def interact(self, actor: Entity) -> bool:
        if self.entity.distance_to(actor) > self.distance:
            return False
        self.callback(actor)
        return True


EnemyBehavior = Literal["idle", "chase"]


class Enemy(Player):
    """Optional visible enemy preset with native character movement."""

    def __init__(
        self,
        *,
        health: float = 100,
        speed: float = 3,
        behavior: EnemyBehavior = "chase",
        target: Entity | None = None,
        stop_distance: float = 1.25,
        color: str = "red",
        **kwargs: object,
    ) -> None:
        if behavior not in ("idle", "chase"):
            raise ValueError("behavior must be 'idle' or 'chase'")
        if target is not None and not isinstance(target, Entity):
            raise TypeError("target must be an rix.Entity or None")
        self.behavior: EnemyBehavior = behavior
        self.target = target
        self.stop_distance = _non_negative(stop_distance, "stop distance")
        super().__init__(move_speed=speed, controls=False, **kwargs)  # type: ignore[arg-type]
        self.health = Health(self, health)
        self.visual = Cube(
            parent=self,
            position=(0, 0.9, 0),
            scale=(0.8, 1.8, 0.8),
            color=color,
            collider=False,
            name=f"{self.name} visual",
        )

    def fixed_update(self, _delta_seconds: float) -> None:
        if not self.health.alive or self.behavior == "idle" or self.target is None:
            self.move((0, 0, 0))
            return
        delta = self.target.world_position - self.world_position
        if delta.length <= self.stop_distance:
            self.move((0, 0, 0))
            return
        heading = math.degrees(math.atan2(-delta.x, -delta.z))
        self.move((0, 0, 1), heading_degrees=heading)


__all__ = [
    "DamageEvent",
    "DeathEvent",
    "Enemy",
    "EnemyBehavior",
    "Health",
    "HitscanWeapon",
    "Interaction",
    "Respawner",
    "Scoreboard",
    "ShotResult",
    "SpawnPoint",
    "Team",
    "TeamRoster",
]
