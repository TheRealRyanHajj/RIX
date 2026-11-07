"""Interactive D3D11 validation for RIX skyboxes and multiple lights."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import threading
import time

import rix as e3


def build_scene(sky_kind: str = "procedural") -> tuple[e3.Scene, list[e3.Light]]:
    scene = e3.Scene("Advanced lighting and sky")
    scene.camera = e3.Camera(position=(11, 7, 15), vertical_fov_degrees=58).look_at(
        (0, 1, 0)
    )
    generated = Path("build/generated-sky")
    if sky_kind == "panorama":
        scene.skybox = e3.Skybox(
            panorama=generated / "lighting-panorama.png", brightness=0.8
        )
    elif sky_kind == "cubemap":
        scene.skybox = e3.Skybox(cubemap=generated / "lighting-cubemap", brightness=0.8)
    else:
        scene.skybox = e3.Skybox(
            top="#2366b1", horizon="#b7d9f3", bottom="#101624", brightness=0.8
        )
    with scene:
        e3.Light("ambient", color="#8aa4cc", intensity=0.12)
        e3.Light(
            "directional", rotation=(-48, -35, 0), intensity=1.0,
            casts_shadows=True, shadow_resolution=2048,
        )
        points = [
            e3.Light("point", color="red", intensity=12, range=11, position=(4, 3, 0)),
            e3.Light("point", color="green", intensity=12, range=11, position=(-2, 3, 4)),
            e3.Light(
                "point", color="blue", intensity=12, range=11, position=(-2, 3, -4),
                casts_shadows=True, shadow_resolution=512,
            ),
        ]
        spot = e3.Light(
            "spot", color="#ffd8a0", intensity=20, position=(0, 8, 3),
            range=18, inner_angle=24, angle=48, casts_shadows=True,
            shadow_resolution=1024,
        )
        spot.look_at((0, 0, 0))
        e3.Plane(size=(24, 24), y=-0.05, color="#46505d", roughness=0.85)
        for z in range(-2, 3):
            for x in range(-3, 4):
                e3.Cube(
                    position=(x * 2.1, 0.7 + ((x + z) & 1) * 0.35, z * 2.1),
                    size=(1.25, 1.4 + ((x - z) & 1) * 0.7, 1.25),
                    color=(0.55 + (x + 3) * 0.045, 0.42, 0.3 + (z + 2) * 0.08),
                    roughness=0.35 + ((x + z) & 1) * 0.4,
                    metallic=0.15 + ((x - z) & 1) * 0.55,
                )
    scene.hud.text(
        f"{sky_kind.title()} sky | 3 point lights | shadowed sun, spot, and point",
        position=(20, 18), font_size=20,
    )
    return scene, points


def run(seconds: float | None, sky_kind: str = "procedural") -> None:
    game = e3.Game(
        "RIX — Lighting and Sky", (1280, 720), vsync=True,
        graphics_preset="high", auto_setup=False,
    )
    scene, points = build_scene(sky_kind)
    game.load_scene(scene)
    elapsed = 0.0

    @game.update
    def animate(dt: float) -> None:
        nonlocal elapsed
        elapsed += dt
        for index, light in enumerate(points):
            angle = elapsed * (0.45 + index * 0.08) + index * math.tau / 3
            light.position = (math.cos(angle) * 5.5, 2.5 + index * 0.6,
                              math.sin(angle) * 5.5)
        if scene.skybox is not None:
            scene.skybox.rotation = elapsed * 3.0

    if seconds is not None:
        threading.Thread(
            target=lambda: (time.sleep(seconds), game.stop()), daemon=True
        ).start()
    game.run()
    stats = game.renderer_stats
    print(
        "lighting_sky_example: PASS "
        f"frames={game.frame_count} lights="
        f"{stats.active_directional_lights}/{stats.active_point_lights}/"
        f"{stats.active_spot_lights} culled={stats.culled_lights} "
        f"shadow_passes={stats.shadow_passes} shadow_bytes={stats.shadow_memory_bytes}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=None)
    parser.add_argument(
        "--sky", choices=("procedural", "panorama", "cubemap"),
        default="procedural",
    )
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(arguments.seconds, arguments.sky)


if __name__ == "__main__":
    main()
