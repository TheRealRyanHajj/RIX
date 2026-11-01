"""Visible Phase 1.9 culling/instancing diagnostic; excluded from pytest."""

from __future__ import annotations

import argparse
import threading
import time

from easy3d import Camera, Cube, Game, Light, Scene


def main(*, seconds: float = 5.0) -> None:
    scene = Scene("renderer optimization diagnostic")
    scene.camera = Camera(position=(0, 1.5, 8)).look_at((0, 0, 0))
    with scene:
        Light("ambient", intensity=0.2)
        Light("directional", intensity=0.9, rotation=(-40, -30, 0))
        Cube(position=(-1.1, 0, 0), color=(0.2, 0.7, 0.95))
        Cube(position=(1.1, 0, 0), color=(0.2, 0.7, 0.95))
        Cube(position=(100, 0, 0), color=(0.2, 0.7, 0.95))
        Cube(position=(-100, 0, 0), color=(0.2, 0.7, 0.95))
        Cube(position=(0, 0, 20), color=(0.2, 0.7, 0.95))

    game = Game("Easy3D culling + instancing", (960, 540), vsync=False)
    game.load_scene(scene)

    def stop_later() -> None:
        time.sleep(seconds)
        game.stop()

    threading.Thread(target=stop_later, daemon=True).start()
    game.run()
    stats = game.renderer_stats
    if stats.visible_instances != 2 or stats.culled_instances != 3:
        raise RuntimeError(f"unexpected culling counters: {stats}")
    if stats.draw_calls != 1 or stats.instanced_draw_calls != 1:
        raise RuntimeError(f"shared cubes were not instanced: {stats}")
    print(f"renderer_optimization: PASS frames={game.frame_count} stats={stats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5.0)
    arguments = parser.parse_args()
    if arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    main(seconds=arguments.seconds)
