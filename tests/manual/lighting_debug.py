"""Visible Phase 1.8 lighting/camera/debug diagnostic; excluded from pytest."""

from __future__ import annotations

import argparse
import threading
import time

from easy3d import Camera, Cube, Game, Light, MeshRenderer, Plane, Scene, Sphere, debug


def main(*, seconds: float = 10.0, preset: str = "medium") -> None:
    scene = Scene("lighting and debug drawing")
    camera = Camera(position=(0, 3.2, 9), vertical_fov_degrees=52)
    camera.look_at((0, 0.35, 0))
    scene.camera = camera

    with scene:
        Light("ambient", color=(0.55, 0.65, 1.0), intensity=0.18)
        Light("directional", color=(1.0, 0.88, 0.70), intensity=0.95,
              rotation=(-35, -35, 0))
        Plane(position=(0, -1, 0), size=(10, 8), color=(0.25, 0.28, 0.35))
        Cube(position=(-2.2, 0, 0), rotation=(15, 35, 0),
             size=(1.25, 1.8, 1.25), color=(0.90, 0.24, 0.16))
        sphere = Sphere(position=(0, 0, 0), radius=1.0, color=(0.18, 0.66, 0.95))
        surface = sphere.get_component(MeshRenderer)
        assert surface is not None
        surface.metallic = 0.75
        surface.roughness = 0.22
        Cube(position=(2.2, 0, 0), rotation=(0, -25, 8),
             size=(1.25, 1.8, 1.25), color=(0.30, 0.92, 0.42), lit=False)
        debug.axes((-3.8, -0.95, 1.5), size=1.2)
        debug.line((-4.5, -0.98, -2.0), (4.5, -0.98, -2.0),
                   color=(1.0, 0.85, 0.20), depth_test=False)

    game = Game(
        "Easy3D lighting + camera + debug drawing",
        (960, 540),
        vsync=False,
        graphics_preset=preset,  # type: ignore[arg-type]
    )
    game.load_scene(scene)

    def stop_later() -> None:
        time.sleep(seconds)
        game.stop()

    threading.Thread(target=stop_later, daemon=True).start()
    game.run()
    stats = game.renderer_stats
    if preset in ("high", "ultra") and not stats.shadows:
        raise RuntimeError(f"requested shadow preset fell back on this device: {stats}")
    print(
        "lighting_debug: PASS "
        f"frames={game.frame_count} debug_lines={scene.debug_line_count} stats={stats}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--preset", choices=("low", "medium", "high", "ultra"), default="medium")
    arguments = parser.parse_args()
    if arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    main(seconds=arguments.seconds, preset=arguments.preset)
