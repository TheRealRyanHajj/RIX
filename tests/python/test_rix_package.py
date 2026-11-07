from __future__ import annotations

import subprocess
import sys

import pygame
import pytest

import rix


def test_rix_is_the_authoritative_package() -> None:
    assert rix.engine_version() == rix.__version__
    assert rix._rix.__name__ == "rix._rix"  # type: ignore[attr-defined]


def test_pinned_pygame_ce_runtime() -> None:
    assert pygame.version.ver == "2.5.8"
    assert pygame.get_sdl_version()[:2] == (2, 32)


def test_easy3d_compatibility_shim_warns_and_shares_native_module() -> None:
    code = """
import sys, warnings
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    import easy3d
    import easy3d._easy3d
    import rix
assert easy3d.Cube is rix.Cube
assert easy3d._easy3d is rix._rix
assert any(item.category is DeprecationWarning for item in caught)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_standalone_import_and_primitive_do_not_require_pygame() -> None:
    code = """
import sys
sys.modules['pygame'] = None
import rix
scene = rix.Scene('no pygame')
cube = rix.Cube(scene=scene, color='orange')
assert cube.is_alive
try:
    rix.SurfaceTexture(object())
except ImportError as error:
    assert 'rix[pygame]' in str(error)
else:
    raise AssertionError('SurfaceTexture unexpectedly worked without Pygame')
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_pygame_vectors_are_accepted_by_public_vectors_and_entities() -> None:
    vector = pygame.Vector3(1.0, 2.0, 3.0)
    assert tuple(rix.Vec3.from_value(vector)) == (1.0, 2.0, 3.0)

    scene = rix.Scene("pygame vectors")
    cube = rix.Cube(scene=scene, position=vector)
    assert tuple(cube.position) == pytest.approx((1.0, 2.0, 3.0))
    cube.position = pygame.Vector3(4.0, 5.0, 6.0)
    assert tuple(cube.position) == pytest.approx((4.0, 5.0, 6.0))
    scene.close()

