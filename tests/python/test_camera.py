from __future__ import annotations

import math

import pytest

from rix import Camera, Vec3


def test_default_camera_basis_and_view_matrix() -> None:
    camera = Camera(position=(0.0, 0.0, 5.0))

    assert camera.forward.almost_equal(Vec3(0.0, 0.0, -1.0))
    assert camera.right.almost_equal(Vec3(1.0, 0.0, 0.0))
    assert camera.up.almost_equal(Vec3(0.0, 1.0, 0.0))
    assert len(camera.view_matrix()) == 16
    assert camera.view_matrix()[14] == pytest.approx(-5.0)


def test_look_at_updates_orientation() -> None:
    camera = Camera(position=(3.0, 2.0, 5.0))
    camera.look_at((0.0, 0.0, 0.0))

    expected = (Vec3(0.0, 0.0, 0.0) - camera.position).normalized()
    assert camera.forward.almost_equal(expected, tolerance=1.0e-5)


def test_projection_uses_resolution_and_configurable_clipping() -> None:
    camera = Camera(vertical_fov_degrees=70.0, near_plane=0.25, far_plane=250.0)
    square = camera.projection_matrix((600, 600))
    wide = camera.projection_matrix((1200, 600))

    assert Camera.aspect_ratio((1200, 600)) == pytest.approx(2.0)
    assert wide[0] == pytest.approx(square[0] * 0.5)
    assert wide[5] == pytest.approx(square[5])
    assert all(math.isfinite(value) for value in wide)


def test_orthographic_projection_and_scene_round_trip() -> None:
    from rix import Scene

    camera = Camera(
        position=(2.0, 3.0, 4.0),
        projection="orthographic",
        orthographic_height=12.0,
        near_plane=0.5,
        far_plane=100.0,
    )
    square = camera.projection_matrix((600, 600))
    wide = camera.projection_matrix((1200, 600))
    assert wide[0] == pytest.approx(square[0] * 0.5)
    assert wide[5] == pytest.approx(1.0 / 6.0)

    scene = Scene()
    scene.camera = camera
    restored = scene.camera
    assert restored.projection == "orthographic"
    assert restored.orthographic_height == pytest.approx(12.0)
    assert restored.position == camera.position


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vertical_fov_degrees": 0.0},
        {"vertical_fov_degrees": 180.0},
        {"near_plane": 0.0},
        {"near_plane": 2.0, "far_plane": 1.0},
        {"orthographic_height": 0.0},
    ],
)
def test_invalid_camera_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Camera(**kwargs)


def test_invalid_resolution_and_look_at_are_rejected() -> None:
    camera = Camera()
    with pytest.raises(ValueError):
        camera.projection_matrix((1280, 0))
    with pytest.raises(ValueError):
        camera.look_at(camera.position)
    with pytest.raises(ValueError, match="projection"):
        Camera(projection="panoramic")  # type: ignore[arg-type]
