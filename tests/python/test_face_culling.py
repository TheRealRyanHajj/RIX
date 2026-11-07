from pathlib import Path
from typing import Callable

import pytest

import rix as e3


PrimitiveFactory = Callable[..., e3.Entity]


@pytest.mark.parametrize("factory", [e3.Cube, e3.Plane, e3.Sphere])
def test_primitive_culling_defaults_shorthand_and_modes(
    factory: PrimitiveFactory,
) -> None:
    scene = e3.Scene("culling")
    default = factory(scene=scene, collider=False)
    double = factory(scene=scene, collider=False, double_sided=True)
    front = factory(scene=scene, collider=False, cull_mode="front")
    explicit_none = factory(scene=scene, collider=False, cull_mode="none")

    assert default.cull_mode == "back"
    assert default.double_sided is False
    assert double.cull_mode == "none" and double.double_sided is True
    assert front.cull_mode == "front" and front.double_sided is False
    assert explicit_none.cull_mode == "none"


def test_conflicting_and_invalid_culling_arguments_are_actionable() -> None:
    scene = e3.Scene("validation")
    with pytest.raises(ValueError, match="conflicts"):
        e3.Cube(scene=scene, cull_mode="front", double_sided=True)
    with pytest.raises(ValueError, match="conflicts"):
        e3.Cube(scene=scene, cull_mode="none", double_sided=False)
    with pytest.raises(ValueError, match="back,.*front,.*none|back.*front.*none"):
        e3.Cube(scene=scene, cull_mode="sideways")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="double_sided must be a bool"):
        e3.Cube(scene=scene, double_sided=1)  # type: ignore[arg-type]

    # Equivalent explicit values are not conflicts.
    assert e3.Cube(
        scene=scene, collider=False, cull_mode="none", double_sided=True
    ).cull_mode == "none"
    assert e3.Cube(
        scene=scene, collider=False, cull_mode="back", double_sided=False
    ).cull_mode == "back"


def test_runtime_entity_and_component_culling_share_one_native_state() -> None:
    scene = e3.Scene("runtime")
    cube = e3.Cube(scene=scene, collider=True)
    collider = cube.get_component(e3.Collider)
    renderer = cube.get_component(e3.MeshRenderer)
    assert collider is not None and renderer is not None

    cube.double_sided = True
    assert cube.cull_mode == renderer.cull_mode == "none"
    assert renderer.double_sided is True

    renderer.cull_mode = "front"
    assert cube.cull_mode == "front" and cube.double_sided is False

    renderer.double_sided = False
    assert cube.cull_mode == renderer.cull_mode == "back"
    assert cube.get_component(e3.Collider) is not None
    assert cube.get_component(e3.Collider).shape == collider.shape  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="cull_mode"):
        renderer.cull_mode = "invalid"  # type: ignore[assignment]
    with pytest.raises(TypeError, match="double_sided"):
        renderer.double_sided = "yes"  # type: ignore[assignment]


def _write_obj(path: Path) -> None:
    path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")


def test_model_culling_override_and_scene_cleanup(tmp_path: Path) -> None:
    path = tmp_path / "triangle.obj"
    _write_obj(path)
    scene = e3.Scene("models")
    inherited = e3.Model(path, scene=scene, collider=False)
    double = e3.Model(path, scene=scene, collider=False, double_sided=True)
    front = e3.Model(path, scene=scene, collider=False, cull_mode="front")

    assert inherited.cull_mode == "back"
    assert double.cull_mode == "none"
    assert front.cull_mode == "front"
    scene.clear()
    assert scene.entity_count == 0


def test_cull_mode_type_is_public() -> None:
    mode: e3.CullMode = "none"
    assert mode == "none"
