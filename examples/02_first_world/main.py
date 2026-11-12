"""RIX Phase 1 first-world scene using only the public Python API."""

# Usage: from the repository root, run:
#   python examples/02_first_world/main.py

from __future__ import annotations

import argparse
import base64
import math
import tempfile
import threading
import time
from pathlib import Path

from rix import Camera, Cube, Entity, Game, Light, Model, Plane, Scene, Sphere, debug


_CHECKER_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAAXNSR0IArs4c6QAAAARn"
    "QU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAXSURBVBhXY/jPwPCfoYHh"
    "PwMDw38wAABD1Al4TlSdlQAAAABJRU5ErkJggg=="
)


class OrbitCamera(Entity):
    """Small Phase 2 script proving safe per-frame scene-camera mutation."""

    def __init__(self, *, scene: Scene) -> None:
        super().__init__("Orbit camera", scene=scene)
        self._angle = math.atan2(11.0, 8.5)

    def update(self, dt: float) -> None:
        self._angle += dt * 0.22
        camera = Camera(
            position=(
                math.cos(self._angle) * 13.9,
                6.0,
                math.sin(self._angle) * 13.9,
            ),
            vertical_fov_degrees=52.0,
        )
        camera.look_at((0.0, 0.5, 0.0))
        self.scene.camera = camera


def _write_example_assets(directory: Path) -> tuple[Path, Path]:
    """Create deterministic tiny assets without third-party Python packages."""

    texture = directory / "checker.png"
    texture.write_bytes(base64.b64decode(_CHECKER_PNG))
    (directory / "pyramid.mtl").write_text(
        "newmtl Checker\nKd 1 1 1\nmap_Kd checker.png\n",
        encoding="utf-8",
    )
    model = directory / "pyramid.obj"
    model.write_text(
        "mtllib pyramid.mtl\n"
        "o Pyramid\n"
        "v -1 0 -1\nv 1 0 -1\nv 1 0 1\nv -1 0 1\nv 0 2 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvt 0.5 0.5\n"
        "vn 0 -1 0\nvn 0 0.447 -0.894\nvn 0.894 0.447 0\n"
        "vn 0 0.447 0.894\nvn -0.894 0.447 0\n"
        "usemtl Checker\n"
        "f 1/1/1 4/4/1 3/3/1 2/2/1\n"
        "f 1/1/2 2/2/2 5/5/2\n"
        "f 2/1/3 3/2/3 5/5/3\n"
        "f 3/1/4 4/2/4 5/5/4\n"
        "f 4/1/5 1/2/5 5/5/5\n",
        encoding="utf-8",
    )
    return texture, model


def run(*, seconds: float | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rix-first-world-") as temporary:
        texture, model = _write_example_assets(Path(temporary))
        scene = Scene("First world")
        camera = Camera(position=(8.5, 6.0, 11.0), vertical_fov_degrees=52.0)
        camera.look_at((0.0, 0.5, 0.0))
        scene.camera = camera

        with scene:
            OrbitCamera(scene=scene)
            Light("ambient", color=(0.45, 0.55, 0.8), intensity=0.24)
            Light(
                "directional",
                color=(1.0, 0.88, 0.68),
                intensity=1.0,
                rotation=(-42.0, -32.0, 0.0),
            )
            Plane(
                position=(0.0, -1.0, 0.0),
                size=(14.0, 12.0),
                color=(0.42, 0.48, 0.38),
                texture=texture,
                name="Textured ground",
            )
            Model(model, position=(0.0, -1.0, 0.0), name="Loaded OBJ pyramid")
            Cube(
                position=(-3.0, 0.0, -0.5),
                rotation=(8.0, 28.0, 0.0),
                size=(1.4, 2.0, 1.4),
                color=(0.92, 0.26, 0.18),
                name="Red cube",
            )
            Sphere(
                position=(3.0, 0.0, 0.5),
                radius=1.1,
                color=(0.18, 0.58, 0.95),
                name="Blue sphere",
            )
            debug.axes((-5.0, -0.95, 3.0), size=1.5)

        game = Game("RIX — First World", (1280, 720), vsync=True)
        game.load_scene(scene)

        if seconds is not None:
            def stop_later() -> None:
                time.sleep(seconds)
                game.stop()

            threading.Thread(target=stop_later, daemon=True).start()

        game.run()
        stats = game.renderer_stats
        scheduler_stats = game.scheduler_stats
        unloaded = game.unload_scene(clear=True)
        if unloaded is not scene or scene.entity_count != 0:
            raise RuntimeError("first-world scene did not tear down cleanly")
        scene.close()
        print(
            "first_world: PASS "
            f"frames={game.frame_count} draw_calls={stats.draw_calls} "
            f"visible={stats.visible_instances} culled={stats.culled_instances} "
            f"fixed_ticks={scheduler_stats.fixed_ticks} "
            f"update_calls={scheduler_stats.callbacks.get('update').calls} "
            f"scene_closed={scene.closed}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="automatically close after N seconds (default: close interactively)",
    )
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(seconds=arguments.seconds)


if __name__ == "__main__":
    main()
