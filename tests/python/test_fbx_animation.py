from __future__ import annotations

import os
from pathlib import Path

import pytest

from rix import FbxInfo, Model, Scene, load_fbx


DEFAULT_ANIMATION_TEST = Path(
    r"C:\Users\Ryan\Desktop\code\code\python\rix things\animation test"
)
ANIMATION_TEST = Path(
    os.environ.get("RIX_ANIMATION_TEST_DIR", DEFAULT_ANIMATION_TEST)
)
ASSETS = ANIMATION_TEST / "assets"
YBOT = ASSETS / "YBot.fbx"
THRILLER = ASSETS / "Thriller Animation.fbx"

pytestmark = pytest.mark.skipif(
    not (YBOT.is_file() and THRILLER.is_file()),
    reason=(
        "external YBot/Thriller acceptance assets are unavailable; set "
        "RIX_ANIMATION_TEST_DIR to the animation-test project"
    ),
)


def test_fbx_metadata_uses_shared_model_animation_types() -> None:
    character: FbxInfo = load_fbx(YBOT)
    motion = load_fbx(THRILLER)

    assert character.triangle_count == 55_320
    assert character.skeleton is not None
    assert len(character.skeleton.joints) == 52
    assert len(character.parts) == 2
    assert motion.triangle_count == 0
    assert motion.skeleton is not None
    assert len(motion.skeleton.joints) == 65
    assert len(motion.animations) == 1
    assert motion.animations[0].duration == pytest.approx(18.833334, rel=1e-5)

    start = motion.animations[0].sample(motion.skeleton, 0.0, loop=False)
    middle = motion.animations[0].sample(
        motion.skeleton, motion.animations[0].duration * 0.5, loop=False
    )
    assert any(a.position != b.position or a.rotation != b.rotation
               for a, b in zip(start, middle, strict=True))


def test_model_external_clip_playback_controls_and_callback() -> None:
    scene = Scene("FBX animation")
    model = Model(YBOT, collider=False, scene=scene)
    model.add_animation("Thriller", THRILLER)

    assert "mixamo.com" in model.animation_clips
    assert "Thriller" in model.animation_clips
    model.play("Thriller", loop=True, speed=1.25, blend=0.2)
    scene._native.step_physics(1.0 / 60.0)
    assert model.current_animation == "Thriller"
    assert model.animation_state == "playing"
    assert model.animation_time > 0
    assert model.animation_speed == pytest.approx(1.25)
    assert model.animation_duration == pytest.approx(18.833334, rel=1e-5)
    assert model.animation_skinning == "gpu"

    model.pause_animation()
    paused = model.animation_time
    scene._native.step_physics(1.0 / 60.0)
    assert model.animation_state == "paused"
    assert model.animation_time == paused
    model.resume_animation()
    scene._native.step_physics(1.0 / 60.0)
    assert model.animation_time > paused
    model.stop_animation()
    assert model.animation_state == "stopped"
    assert model.current_animation is None

    completed: list[Model] = []
    model.play("Thriller", loop=False, speed=2.0, on_complete=completed.append)
    scene._native.step_physics(10.0)
    model.late_update(0.0)
    assert completed == [model]
    model.late_update(0.0)
    assert completed == [model]


def test_root_motion_moves_owner_without_accumulating_visual_root() -> None:
    scene = Scene("FBX root motion")
    model = Model(YBOT, collider=False, scene=scene)
    model.add_animation("Thriller", THRILLER)
    before = model.world_position

    model.play("Thriller", root_motion=True)
    scene._native.step_physics(1.0)

    moved = model.world_position
    assert abs(moved.x - before.x) + abs(moved.z - before.z) > 0.01
    assert moved.y == pytest.approx(before.y, abs=1e-6)

    model.pause_animation()
    paused = model.world_position
    scene._native.step_physics(0.5)
    assert model.world_position == paused

    model.resume_animation()
    scene._native.step_physics(0.25)
    assert model.world_position != paused

    before_restart = model.world_position
    model.play("Thriller", root_motion=True)
    assert model.world_position == before_restart
    scene._native.step_physics(model.animation_duration + 0.125)
    assert (model.world_position - before_restart).length > 0.01
    assert model.world_position.y == pytest.approx(before.y, abs=1e-6)


def test_animation_api_rejects_invalid_inputs() -> None:
    scene = Scene("FBX validation")
    model = Model(YBOT, collider=False, scene=scene)
    with pytest.raises(ValueError, match="non-empty"):
        model.add_animation("", THRILLER)
    with pytest.raises(Exception, match="no animation clip"):
        model.play("missing")
    with pytest.raises(ValueError, match="finite and nonzero"):
        model.play("mixamo.com", speed=0)
    with pytest.raises(ValueError, match="non-negative"):
        model.play("mixamo.com", blend=-1)


def test_instances_loop_restart_reverse_and_keep_independent_state() -> None:
    scene = Scene("independent FBX animation")
    first = Model(YBOT, collider=False, scene=scene)
    second = Model(YBOT, collider=False, scene=scene)
    for model in (first, second):
        model.add_animation("Thriller", THRILLER)

    first.play("Thriller", speed=1.0)
    second.play("Thriller", speed=0.5)
    scene._native.step_physics(1.0)
    assert first.animation_time == pytest.approx(1.0)
    assert second.animation_time == pytest.approx(0.5)

    first.play("Thriller", speed=-1.0)
    assert first.animation_time == pytest.approx(first.animation_duration)
    scene._native.step_physics(0.25)
    assert first.animation_time == pytest.approx(first.animation_duration - 0.25)

    first.play("Thriller", loop=True)
    scene._native.step_physics(first.animation_duration + 0.125)
    assert first.animation_time == pytest.approx(0.125, abs=1e-4)
    first.play("Thriller")
    assert first.animation_time == 0.0


def test_animation_only_fbx_cannot_be_created_as_visible_model() -> None:
    scene = Scene("animation-only validation")
    with pytest.raises(Exception, match="animation-only asset"):
        Model(THRILLER, collider=False, scene=scene)
