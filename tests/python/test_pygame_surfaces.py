from __future__ import annotations

import gc

import pygame

import rix


def test_surface_texture_copies_rgba_alpha_and_pitch_safely() -> None:
    backing = pygame.Surface((4, 2), pygame.SRCALPHA, 32)
    backing.fill((9, 8, 7, 6))
    surface = backing.subsurface((1, 0, 2, 2))
    surface.set_at((0, 0), (1, 2, 3, 4))
    surface.set_at((1, 0), (10, 20, 30, 40))
    surface.set_at((0, 1), (50, 60, 70, 80))
    surface.set_at((1, 1), (90, 100, 110, 120))

    texture = rix.SurfaceTexture(surface)
    assert texture.size == (2, 2)
    assert texture._native._rgba8() == bytes(
        (1, 2, 3, 4, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120)
    )

    del surface, backing
    gc.collect()
    assert texture._native._rgba8()[:4] == bytes((1, 2, 3, 4))


def test_surface_texture_updates_explicitly_and_can_resize() -> None:
    first = pygame.Surface((1, 1), pygame.SRCALPHA)
    first.fill((255, 0, 0, 128))
    texture = rix.SurfaceTexture(first, srgb=False)
    revision = texture.revision

    second = pygame.Surface((3, 2), pygame.SRCALPHA)
    second.fill((0, 255, 0, 64))
    texture.update(second)
    assert texture.size == (3, 2)
    assert texture.revision == revision + 1
    assert texture._native._rgba8() == bytes((0, 255, 0, 64)) * 6


def test_primitive_accepts_surface_and_exposes_updatable_texture() -> None:
    scene = rix.Scene("surface primitive")
    surface = pygame.Surface((8, 8), pygame.SRCALPHA)
    surface.fill((20, 40, 60, 200))
    cube = rix.Cube(scene=scene, texture=surface)
    assert isinstance(cube.texture, rix.SurfaceTexture)
    assert cube.get_component(rix.MeshRenderer) is not None
    scene.close()


def test_billboard_is_collidable_by_default() -> None:
    scene = rix.Scene("billboard collider")
    image = pygame.Surface((8, 16), pygame.SRCALPHA)
    billboard = rix.Billboard(image=image, scene=scene)
    assert billboard.get_component(rix.Collider) is not None
    scene.close()

