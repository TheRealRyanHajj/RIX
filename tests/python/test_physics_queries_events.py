from __future__ import annotations

import pytest

from rix import Collider, CollisionEvent, Cube, Entity, Game, Rigidbody, Scene, Sphere
from rix import physics


def _begin(scene: Scene) -> Game:
    game = Game(fixed_hz=60)
    game.load_scene(scene)
    game._scheduler.begin_run()
    return game


def _tick(game: Game, count: int = 1) -> None:
    assert game.scene is not None
    for _ in range(count):
        game._scheduler.advance(game.scene, 1.0 / 60.0)


def test_raycast_and_overlap_queries_are_sorted_filtered_snapshots() -> None:
    scene = Scene()
    near = Sphere(position=(0.0, 0.0, 0.0), radius=0.5, collider=True, scene=scene)
    far = Cube(position=(0.0, 0.0, -3.0), collider=True, scene=scene)
    trigger = Entity("trigger", scene=scene)
    trigger.position = (3.0, 0.0, 0.0)
    trigger.add_component(Collider, trigger=True, layer="sensor")

    hits = physics.raycast_all(scene, (0.0, 0.0, 3.0), (0.0, 0.0, -1.0), 10.0)
    assert [hit.entity for hit in hits] == [near, far]
    assert hits[0].distance < hits[1].distance
    assert hits[0].normal.z > 0.9
    assert physics.raycast(
        scene,
        (0.0, 0.0, 3.0),
        (0.0, 0.0, -1.0),
        10.0,
        exclude=near,
    ).entity == far  # type: ignore[union-attr]

    sphere_hits = physics.overlap_sphere(scene, near.position, 0.25)
    assert [hit.entity for hit in sphere_hits] == [near]
    box_hits = physics.overlap_box(
        scene, (0.0, 0.0, -1.5), (1.0, 1.0, 2.0)
    )
    assert {hit.entity for hit in box_hits} == {near, far}
    assert physics.overlap_sphere(scene, trigger.position, 0.25)
    assert not physics.overlap_sphere(
        scene, trigger.position, 0.25, include_triggers=False
    )
    assert not physics.raycast_all(
        scene,
        (0.0, 0.0, 3.0),
        (0.0, 0.0, -1.0),
        10.0,
        layers=("dynamic",),
    )
    sphere_cast_hits = physics.sphere_cast_all(
        scene, (0.0, 0.0, 3.0), 0.2, (0.0, 0.0, -1.0), 10.0
    )
    assert [hit.entity for hit in sphere_cast_hits] == [near, far]
    capsule_hit = physics.capsule_cast(
        scene,
        (0.0, 0.0, 3.0),
        0.2,
        1.0,
        (0.0, 0.0, -1.0),
        10.0,
    )
    assert capsule_hit is not None and capsule_hit.entity == near

    with pytest.raises(ValueError, match="nonzero|direction"):
        physics.raycast(scene, (0, 0, 0), (0, 0, 0), 1.0)
    with pytest.raises(ValueError, match="layers"):
        physics.overlap_sphere(scene, (0, 0, 0), 1.0, layers=("bad",))  # type: ignore[arg-type]


def test_collision_enter_stay_exit_dispatch_after_fixed_step() -> None:
    class Ball(Entity):
        def __init__(self, *, scene: Scene) -> None:
            self.events: list[tuple[str, CollisionEvent]] = []
            super().__init__("ball", scene=scene)

        def on_collision_enter(self, event: CollisionEvent) -> None:
            self.events.append(("enter", event))

        def on_collision_stay(self, event: CollisionEvent) -> None:
            self.events.append(("stay", event))

        def on_collision_exit(self, event: CollisionEvent) -> None:
            self.events.append(("exit", event))

    scene = Scene()
    floor = Cube(position=(0.0, -0.5, 0.0), size=(5.0, 1.0, 5.0), collider=True, scene=scene)
    ball = Ball(scene=scene)
    ball.position = (0.0, 0.7, 0.0)
    ball.add_component(Collider, shape="sphere", radius=0.5)
    body = ball.add_component(Rigidbody)
    game = _begin(scene)

    _tick(game, 30)
    phases = [phase for phase, _ in ball.events]
    assert "enter" in phases
    assert "stay" in phases
    enter = next(event for phase, event in ball.events if phase == "enter")
    assert enter.other == floor
    assert enter.normal.length == pytest.approx(1.0, abs=1.0e-4)

    body.teleport((0.0, 4.0, 0.0))
    _tick(game)
    assert ball.events[-1][0] == "exit"
    assert game.scheduler_stats.callbacks["on_collision_enter"].calls == 1


def test_trigger_enter_stay_exit_uses_trigger_hooks_only() -> None:
    class SensorProbe(Entity):
        def __init__(self, *, scene: Scene) -> None:
            self.phases: list[str] = []
            self.collision_calls = 0
            super().__init__("probe", scene=scene)

        def on_trigger_enter(self, event: CollisionEvent) -> None:
            assert event.other.name == "sensor"
            self.phases.append("enter")

        def on_trigger_stay(self, event: CollisionEvent) -> None:
            self.phases.append("stay")

        def on_trigger_exit(self, event: CollisionEvent) -> None:
            self.phases.append("exit")

        def on_collision_enter(self, event: CollisionEvent) -> None:
            self.collision_calls += 1

    scene = Scene()
    sensor = Entity("sensor", scene=scene)
    sensor.add_component(
        Collider,
        half_extents=(1.0, 1.0, 1.0),
        trigger=True,
        layer="sensor",
    )
    probe = SensorProbe(scene=scene)
    probe.add_component(Collider, shape="sphere", radius=0.5)
    body = probe.add_component(Rigidbody, use_gravity=False)
    game = _begin(scene)

    _tick(game, 2)
    assert probe.phases[:2] == ["enter", "stay"]
    assert probe.collision_calls == 0
    body.teleport((4.0, 0.0, 0.0))
    _tick(game)
    assert probe.phases[-1] == "exit"
