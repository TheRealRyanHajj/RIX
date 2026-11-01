"""Visible Phase 1.7 scene/component diagnostic; excluded from pytest."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time

from easy3d import Cube, Game, Model, Plane, Scene, Sphere


def main(*, seconds: float = 10.0) -> None:
    with TemporaryDirectory(prefix="easy3d_render_components_") as directory:
        model_path = Path(directory) / "pyramid.obj"
        model_path.write_text(
            "v -0.6 0 -0.6\n"
            "v 0.6 0 -0.6\n"
            "v 0.6 0 0.6\n"
            "v -0.6 0 0.6\n"
            "v 0 1.2 0\n"
            "f 4 3 5\n"
            "f 3 2 5\n"
            "f 2 1 5\n"
            "f 1 4 5\n"
            "f 1 2 3 4\n",
            encoding="utf-8",
        )

        scene = Scene("native render components")
        with scene:
            Plane(position=(0, -0.75, 0), size=(10, 8), color=(0.3, 0.35, 0.45))
            Cube(
                position=(-2.4, 0, 0),
                rotation=(0, 35, 0),
                size=(0.8, 1.4, 0.8),
                color=(0.95, 0.3, 0.2),
            )
            Cube(position=(-0.8, 0, 0), color=(0.2, 0.75, 0.95))
            Sphere(position=(0.9, 0, 0), radius=0.65, color=(0.95, 0.75, 0.2))
            Model(model_path, position=(2.5, -0.5, 0), color=(0.5, 0.9, 0.4))

        game = Game("Easy3D native render components", (960, 540), vsync=False)
        game.load_scene(scene)

        def stop_later() -> None:
            time.sleep(seconds)
            game.stop()

        threading.Thread(target=stop_later, daemon=True).start()
        game.run()
        print(f"render_components: PASS frames={game.frame_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    if arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    main(seconds=arguments.seconds)
