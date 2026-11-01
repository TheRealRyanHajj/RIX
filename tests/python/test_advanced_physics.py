from __future__ import annotations

from pathlib import Path

import pytest

from easy3d import Collider, Cube, Entity, Model, PhysicsError, Rigidbody, Scene, Vec3
from easy3d import physics


def _step(scene: Scene, count: int) -> None:
    for _ in range(count):
        scene._native.step_physics(1.0 / 60.0)


def _write_plane(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "v -5 0 -5",
                "v 5 0 -5",
                "v 5 0 5",
                "v -5 0 5",
                "f 1 3 2",
                "f 1 4 3",
            )
        ),
        encoding="utf-8",
    )


def test_capsule_convex_mesh_and_ccd_public_components(tmp_path: Path) -> None:
    mesh_path = tmp_path / "floor.obj"
    _write_plane(mesh_path)
    scene = Scene("advanced shapes")
    mesh = Model(mesh_path, collider="mesh", scene=scene)
    mesh_collider = mesh.get_component(Collider)
    assert mesh_collider is not None and mesh_collider.shape == "mesh"

    capsule = Entity("capsule", scene=scene)
    capsule.position = (-2.0, 4.0, 0.0)
    capsule_collider = capsule.add_component(
        Collider, shape="capsule", radius=0.4, height=2.0
    )
    capsule_body = capsule.add_component(Rigidbody, continuous=True)
    assert capsule_collider.height == pytest.approx(2.0)
    assert capsule_body.continuous

    convex = Entity("convex", scene=scene)
    convex.position = (2.0, 4.0, 0.0)
    convex.add_component(
        Collider,
        shape="convex",
        points=(
            (-0.5, -0.5, -0.5),
            (0.5, -0.5, -0.5),
            (0.5, -0.5, 0.5),
            (-0.5, -0.5, 0.5),
            (-0.5, 0.5, -0.5),
            (0.5, 0.5, -0.5),
            (0.5, 0.5, 0.5),
            (-0.5, 0.5, 0.5),
        ),
    )
    convex.add_component(Rigidbody)
    _step(scene, 240)
    assert capsule.position.y == pytest.approx(1.0, abs=0.06)
    assert convex.position.y == pytest.approx(0.5, abs=0.06)

    with pytest.raises(ValueError, match="triangle mesh colliders must be static"):
        mesh.add_component(Rigidbody)
    assert not mesh.has_component(Rigidbody)


def test_fixed_and_distance_constraint_lifetime_and_validation() -> None:
    scene = Scene("constraints")
    anchor = Cube(position=(0.0, 6.0, 0.0), collider=True, scene=scene)
    hanging = Cube(position=(0.0, 3.0, 0.0), collider=True, scene=scene)
    hanging.add_component(Rigidbody)
    distance = physics.distance_constraint(anchor, hanging)
    assert distance.is_alive and distance.type == "distance"
    _step(scene, 120)
    assert (anchor.position - hanging.position).length == pytest.approx(3.0, abs=0.06)
    distance.remove()
    assert not distance.is_alive
    with pytest.raises(PhysicsError, match="stale"):
        distance.remove()

    welded = Cube(position=(3.0, 6.0, 0.0), collider=True, scene=scene)
    welded.add_component(Rigidbody)
    fixed = physics.fixed_constraint(anchor, welded)
    _step(scene, 60)
    assert welded.position.almost_equal(Vec3(3.0, 6.0, 0.0), 0.06)
    welded.destroy()
    assert not fixed.is_alive

    other_scene = Scene()
    foreign = Cube(collider=True, scene=other_scene)
    with pytest.raises(ValueError, match="different scenes"):
        physics.fixed_constraint(anchor, foreign)
    with pytest.raises(ValueError, match="two different"):
        physics.fixed_constraint(anchor, anchor)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"shape": "capsule", "radius": 0.5, "height": 1.0}, "diameter"),
        ({"shape": "convex"}, "points or a mesh"),
        ({"shape": "mesh"}, "mesh asset"),
        ({"shape": "sphere", "points": ((0, 0, 0),)}, "only valid"),
    ),
)
def test_advanced_collider_validation(kwargs: object, message: str) -> None:
    entity = Entity(scene=Scene())
    with pytest.raises(ValueError, match=message):
        entity.add_component(Collider, **kwargs)  # type: ignore[arg-type]


def test_ccd_rejects_kinematic_body() -> None:
    entity = Entity(scene=Scene())
    entity.add_component(Collider)
    with pytest.raises(ValueError, match="requires a dynamic"):
        entity.add_component(Rigidbody, body_type="kinematic", continuous=True)
