from __future__ import annotations

import gc
import weakref

import pytest

from rix import Cube, Entity, Game, InvalidEntityError, Scene, Vec3


def test_explicit_scene_context_owns_entities() -> None:
    scene = Scene("main")
    with scene:
        first = Entity("first")
        second = Entity("second")

    assert first.scene is scene
    assert first.is_alive
    assert second.is_alive
    assert scene.entity_count == 2
    assert set(scene.entities) == {first, second}
    assert [entity.name for entity in scene] == ["first", "second"]


def test_entity_requires_explicit_scene_outside_context() -> None:
    # Prior tests may intentionally abandon a Game involved in a user-created
    # callback closure. CPython is allowed to defer those cycles; collect them
    # so this test measures the absence of a live default, not GC scheduling.
    gc.collect()
    with pytest.raises(RuntimeError, match="no active scene"):
        Entity()


def test_unreachable_game_callback_adapter_does_not_retain_default_scene() -> None:
    game = Game("weak callback owner")
    game.on_update(lambda _dt: None)
    owner = weakref.ref(game)
    del game

    # Reference counting should release the Game immediately; collect as a
    # cross-interpreter guard for unrelated native wrapper cycles.
    gc.collect()
    assert owner() is None
    with pytest.raises(RuntimeError, match="no active scene"):
        Entity()


def test_nested_scene_context_restores_previous_scene() -> None:
    outer = Scene("outer")
    inner = Scene("inner")
    with outer:
        outer_first = Entity("outer first")
        with inner:
            inner_entity = Entity("inner")
        outer_second = Entity("outer second")

    assert outer_first.scene is outer
    assert outer_second.scene is outer
    assert inner_entity.scene is inner


def test_destroy_invalidates_handle_and_reuse_advances_generation() -> None:
    scene = Scene("reuse")
    entity = scene.create_entity("temporary")
    old_id = entity.id
    entity.destroy()

    assert not entity.is_alive
    with pytest.raises(InvalidEntityError, match="invalid entity handle"):
        _ = entity.name
    with pytest.raises(ReferenceError):
        entity.destroy()

    replacement = scene.create_entity("replacement")
    assert replacement.id != old_id
    assert replacement.is_alive


def test_entity_properties_are_native_and_type_checked() -> None:
    scene = Scene("properties")
    entity = scene.create_entity("before")
    entity.name = "after"
    entity.enabled = False
    entity.visible = False

    assert entity.name == "after"
    assert not entity.enabled
    assert not entity.visible
    assert scene.entities[0] == entity

    with pytest.raises(TypeError):
        entity.enabled = 1  # type: ignore[assignment]
    with pytest.raises(ValueError):
        entity.name = ""


def test_scene_clear_and_close_have_explicit_lifetime() -> None:
    scene = Scene("lifetime")
    entity = scene.create_entity()
    scene.clear()
    assert len(scene) == 0
    assert not entity.is_alive

    scene.create_entity("new")
    scene.close()
    assert scene.closed
    assert len(scene) == 0
    scene.close()
    with pytest.raises(RuntimeError, match="scene is closed"):
        scene.create_entity()


def test_scene_rejects_foreign_entity() -> None:
    first = Scene("first")
    second = Scene("second")
    entity = first.create_entity()
    with pytest.raises(ValueError, match="different scene"):
        second.destroy_entity(entity)


def test_game_enforces_single_scene_owner_and_scene_switching() -> None:
    first_game = Game("first")
    second_game = Game("second")
    first_scene = Scene("first scene")
    second_scene = Scene("second scene")

    first_game.load_scene(first_scene)
    assert first_game.scene is first_scene
    assert first_scene.active
    with pytest.raises(RuntimeError, match="another Game"):
        second_game.load_scene(first_scene)
    with pytest.raises(RuntimeError, match="loaded by a Game"):
        first_scene.close()

    first_game.load_scene(second_scene)
    assert not first_scene.active
    assert second_scene.active
    assert first_game.unload_scene() is second_scene
    assert first_game.scene is None
    assert not second_scene.active


def test_repeated_scene_loading_clears_resources_and_invalidates_handles() -> None:
    game = Game("repeated scene lifecycle")
    stale_entities = []
    for index in range(100):
        scene = Scene(f"cycle {index}")
        cube = Cube(scene=scene)
        game.load_scene(scene)
        assert game.unload_scene(clear=True) is scene
        assert scene.entity_count == 0
        assert not cube.is_alive
        scene.close()
        stale_entities.append(cube)

    assert game.scene is None
    assert all(not entity.is_alive for entity in stale_entities)
    with pytest.raises(InvalidEntityError):
        _ = stale_entities[0].name


def test_scene_gravity_is_per_scene_and_validated() -> None:
    first = Scene("first")
    second = Scene("second")
    assert first.gravity.almost_equal(Vec3(0.0, -9.81, 0.0))
    assert second.gravity.almost_equal(Vec3(0.0, -9.81, 0.0))

    first.gravity = (0.0, -3.0, 1.0)
    assert first.gravity.almost_equal(Vec3(0.0, -3.0, 1.0))
    assert second.gravity.almost_equal(Vec3(0.0, -9.81, 0.0))
    with pytest.raises(ValueError, match="finite"):
        first.gravity = (0.0, float("nan"), 0.0)
