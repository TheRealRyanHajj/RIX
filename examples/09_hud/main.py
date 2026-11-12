"""RIX native HUD, sprite, text, layout, and button example."""

# Usage: from the repository root, run:
#   python examples/09_hud/main.py

from __future__ import annotations

import argparse
import base64
import tempfile
import threading
import time
from pathlib import Path

from rix import Camera, Cube, Game, Light, Plane, Scene


_ICON_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAAXNSR0IArs4c6QAAAARn"
    "QU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAXSURBVBhXY/jPwPCfoYHh"
    "PwMDw38wAABD1Al4TlSdlQAAAABJRU5ErkJggg=="
)


def run(*, seconds: float | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rix-hud-") as temporary:
        icon_path = Path(temporary) / "icon.png"
        icon_path.write_bytes(base64.b64decode(_ICON_PNG))

        scene = Scene("HUD example")
        camera = Camera(position=(5, 3.5, 8))
        camera.look_at((0, 0, 0))
        scene.camera = camera
        with scene:
            Light("ambient", intensity=0.25)
            Light("directional", rotation=(-35, -30, 0))
            Plane(position=(0, -1, 0), size=(10, 8), color=(0.18, 0.22, 0.3))
            Cube(position=(0, 0, 0), rotation=(12, 35, 0), color=(0.2, 0.65, 0.95))

        scene.hud.panel(
            position=(16, 16), size=(310, 108), color=(0.04, 0.06, 0.1, 0.88)
        )
        scene.hud.text("RIX native HUD", position=(34, 30), font_size=28, z_index=1)
        status = scene.hud.text(
            "Click a button", position=(34, 72), color=(0.55, 0.82, 1), z_index=1
        )
        scene.hud.sprite(
            str(icon_path),
            position=(-22, 22),
            size=(72, 72),
            anchor="top_right",
            z_index=2,
        )

        game = Game("RIX — HUD", (960, 540), vsync=True, graphics_preset="medium")
        first = scene.hud.button(
            "Update status",
            on_click=lambda _: setattr(status, "text", "Button clicked"),
            size=(190, 48),
        )
        second = scene.hud.button(
            "Close",
            on_click=lambda _: game.stop(),
            size=(190, 48),
        )
        scene.hud.stack(
            "horizontal", (first, second), anchor="bottom", position=(0, -30), spacing=14
        )
        game.load_scene(scene)

        if seconds is not None:
            threading.Thread(
                target=lambda: (time.sleep(seconds), game.stop()), daemon=True
            ).start()

        game.run()
        stats = game.renderer_stats
        if stats.ui_elements != 6 or stats.ui_draw_calls < 8:
            raise RuntimeError(f"HUD submission counters are incomplete: {stats}")
        print(
            "hud_example: PASS "
            f"frames={game.frame_count} ui_elements={stats.ui_elements} "
            f"ui_draw_calls={stats.ui_draw_calls}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=None)
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(seconds=arguments.seconds)


if __name__ == "__main__":
    main()
