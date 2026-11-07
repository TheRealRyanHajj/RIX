from __future__ import annotations

import pytest

from rix import (
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
        Light("area", scene=scene)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        Light("ambient", intensity=-1, scene=scene)
    assert scene.entity_count == 0

    light = Light(scene=scene)
    light.remove_component(LightComponent)
    assert not light.has_component(LightComponent)
    with pytest.raises(RuntimeError, match="no longer"):
        _ = light.intensity


def test_multiple_point_and_spot_lights_have_live_native_properties() -> None:
    scene = Scene("local lights")
    point = Light(
        "point", scene=scene, position=(1, 2, 3), color="orange",
        intensity=4, range=12, casts_shadows=True, shadow_resolution=512,
    )
    spot = Light(
        "spot", scene=scene, position=(-2, 4, 1), rotation=(-60, 20, 0),
        range=18, inner_angle=20, angle=50,
    )
    second_sun = Light("directional", scene=scene, rotation=(-20, 80, 0))
    assert scene.lights("point") == (point,)
    assert scene.lights("spot") == (spot,)
    assert second_sun in scene.lights("directional")
    assert point.range == pytest.approx(12)
    assert point.casts_shadows is True
    assert point.shadow_resolution == 512
    spot.angle = 60
    spot.inner_angle = 25
    spot.shadow_bias = 0.004
    assert (spot.angle, spot.inner_angle, spot.shadow_bias) == pytest.approx(
        (60, 25, 0.004)
    )
    with pytest.raises(ValueError, match="angles"):
        spot.inner_angle = 80
