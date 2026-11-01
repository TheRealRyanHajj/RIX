from __future__ import annotations

import pytest

from easy3d import (
    Camera,
    Cube,
    Light,
    LightComponent,
    MeshRenderer,
    Scene,
    debug,
)


def test_scene_camera_light_components_and_debug_lines() -> None:
    scene = Scene("lighting")
    camera = Camera(
        position=(1, 4, 9),
        vertical_fov_degrees=50,
        near_plane=0.2,
        far_plane=250,
    ).look_at((0, 1, 0))
    scene.camera = camera
    assert tuple(scene.camera.position) == pytest.approx((1, 4, 9))
    assert scene.camera.quaternion.almost_equal(camera.quaternion)
    assert scene.camera.vertical_fov_degrees == pytest.approx(50)

    with scene:
        ambient = Light("ambient", color=(0.2, 0.3, 0.4), intensity=0.25)
        sun = Light("directional", rotation=(-50, -30, 0), intensity=1.5)
        cube = Cube(lit=False)
        debug.axes(size=2)
        debug.line((0, 0, 0), (0, 2, 0), color=(1, 1, 0), depth_test=False)

    ambient_component = ambient.get_component(LightComponent)
    assert isinstance(ambient_component, LightComponent)
    assert ambient_component.kind == "ambient"
    assert ambient_component.color == pytest.approx((0.2, 0.3, 0.4, 1))
    assert ambient_component.intensity == pytest.approx(0.25)
    sun.intensity = 2
    sun.color = (0.9, 0.8, 0.7)
    assert sun.intensity == pytest.approx(2)
    assert sun.color == pytest.approx((0.9, 0.8, 0.7, 1))
    renderer = cube.get_component(MeshRenderer)
    assert isinstance(renderer, MeshRenderer)
    assert renderer.lit is False
    assert scene.debug_line_count == 4

    with pytest.raises(ValueError, match="distinct"):
        scene.add_debug_line((1, 1, 1), (1, 1, 1))
    with pytest.raises(ValueError, match="non-negative"):
        sun.intensity = -1
    scene.clear_debug_lines()
    assert scene.debug_line_count == 0


def test_light_validation_and_component_removal() -> None:
    scene = Scene("validation")
    with pytest.raises(ValueError, match="light type"):
        Light("point", scene=scene)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        Light("ambient", intensity=-1, scene=scene)
    assert scene.entity_count == 0

    light = Light(scene=scene)
    light.remove_component(LightComponent)
    assert not light.has_component(LightComponent)
    with pytest.raises(RuntimeError, match="no longer"):
        _ = light.intensity
