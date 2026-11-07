from __future__ import annotations

import importlib.util
from pathlib import Path
import threading
from types import ModuleType

from rix import CharacterController, Collider, Game, Rigidbody


def _course_module() -> ModuleType:
    path = Path(__file__).parents[2] / "examples" / "03_obstacle_course" / "main.py"
    spec = importlib.util.spec_from_file_location("rix_obstacle_course", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _advance(game: Game) -> None:
    game._gameplay_thread_id = threading.get_ident()
    game._callback_active = True
    try:
        game._scheduler.advance(game.scene, 1.0 / 60.0)
    finally:
        game._callback_active = False


def test_automated_obstacle_course_reaches_finish_and_tears_down() -> None:
    module = _course_module()
    game = Game("headless course regression")
    scene, player = module.build_course(automated=True)
    game.load_scene(scene)
    game._scheduler.begin_run()

    for _ in range(600):
        _advance(game)
        if player.finished:
            break

    assert player.finished
    assert player.position.z < -17.0
    assert player.has_component(CharacterController)
    assert any(entity.has_component(Collider) for entity in scene.entities)
    assert any(entity.has_component(Rigidbody) for entity in scene.entities)
    assert game.scheduler_stats.fixed_ticks > 0
    assert game.scheduler_stats.callbacks["fixed_update"].calls > 0

    assert game.unload_scene(clear=True) is scene
    assert scene.entity_count == 0
    scene.close()
