from __future__ import annotations

from pathlib import Path

import pytest

from easy3d import Collider, Cube, MeshRenderer, Model, Plane, Scene, Sphere, Vec3


def test_primitive_entities_and_component_lookup() -> None:
    scene = Scene("primitives")
    with scene:
        cube = Cube(position=(1, 2, 3), size=(2, 3, 4), color=(0.2, 0.4, 0.6))
        plane = Plane(size=(10, 20))
        sphere = Sphere(radius=2)

    assert tuple(cube.position) == pytest.approx((1, 2, 3))
    assert tuple(cube.scale) == pytest.approx((2, 3, 4))
    assert tuple(plane.scale) == pytest.approx((10, 1, 20))
    assert tuple(sphere.scale) == pytest.approx((4, 4, 4))

    renderer = cube.get_component(MeshRenderer)
    assert isinstance(renderer, MeshRenderer)
    assert renderer.kind == "cube"
    assert renderer.color == pytest.approx((0.2, 0.4, 0.6, 1.0))
    assert renderer.asset is None
    assert renderer.lit
    renderer.color = (1, 0.5, 0, 0.75)
    renderer.lit = False
    assert renderer.color == pytest.approx((1, 0.5, 0, 0.75))
    assert not renderer.lit

    cube.remove_component(MeshRenderer)
    assert not cube.has_component(MeshRenderer)
    assert cube.get_component(MeshRenderer) is None
    with pytest.raises(ValueError, match="does not have"):
        cube.remove_component(MeshRenderer)


def test_model_entity_and_transactional_constructor_failure(tmp_path: Path) -> None:
    model_path = tmp_path / "triangle.obj"
    model_path.write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vn 0 0 1\nf 1//1 2//1 3//1\n",
        encoding="utf-8",
    )
    scene = Scene("models")
    model = Model(model_path, scene=scene, scale=(2, 2, 2))
    renderer = model.get_component(MeshRenderer)
    assert isinstance(renderer, MeshRenderer)
    assert renderer.kind == "model"
    assert renderer.asset == model_path.resolve()

    before = scene.entity_count
    with pytest.raises(ValueError, match="positive"):
        Sphere(radius=0, scene=scene)
    assert scene.entity_count == before
    with pytest.raises(Exception, match="missing.obj"):
        Model(tmp_path / "missing.obj", scene=scene)
    assert scene.entity_count == before


def test_primitive_collider_convenience_uses_world_meter_dimensions() -> None:
    scene = Scene()
    cube = Cube(size=(2.0, 4.0, 6.0), collider=True, scene=scene)
    plane = Plane(size=(10.0, 8.0), collider=True, scene=scene)
    sphere = Sphere(radius=1.5, collider=True, scene=scene)

    cube_collider = cube.get_component(Collider)
    plane_collider = plane.get_component(Collider)
    sphere_collider = sphere.get_component(Collider)
    assert cube_collider is not None
    assert plane_collider is not None
    assert sphere_collider is not None
    assert cube_collider.half_extents.almost_equal(Vec3(1.0, 2.0, 3.0))
    assert plane_collider.half_extents.almost_equal(Vec3(5.0, 0.05, 4.0))
    assert sphere_collider.shape == "sphere"
    assert sphere_collider.radius == pytest.approx(1.5)


def test_primitive_validation() -> None:
    scene = Scene("validation")
    with pytest.raises(ValueError, match="between 0 and 1"):
        Cube(scene=scene, color=(2, 0, 0))
    with pytest.raises(TypeError, match="plane size"):
        Plane(scene=scene, size=(1, 2, 3))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="lit"):
        Sphere(scene=scene, lit=1)  # type: ignore[arg-type]
    assert scene.entity_count == 0


def test_loaded_running_scene_rejects_public_mutation() -> None:
    class RunningOwner:
        is_running = True

    scene = Scene("running")
    cube = Cube(scene=scene)
    renderer = cube.get_component(MeshRenderer)
    assert isinstance(renderer, MeshRenderer)
    owner = RunningOwner()
    scene._attach(owner)

    with pytest.raises(RuntimeError, match="cannot mutate"):
        Cube(scene=scene)
    with pytest.raises(RuntimeError, match="cannot mutate"):
        cube.position.x += 1
    with pytest.raises(RuntimeError, match="cannot mutate"):
        renderer.color = (1, 0, 0)
    with pytest.raises(RuntimeError, match="cannot mutate"):
        scene.clear()

    scene._detach(owner)
    cube.position.x += 1
    assert cube.position.x == pytest.approx(1)
