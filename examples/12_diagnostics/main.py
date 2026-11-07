"""Structured asset reporting plus the native RIX runtime debug overlay."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import threading
import time

from rix import Cube, DebugOverlay, Game, Light, Plane, Scene, diagnose_asset


def run(*, seconds: float | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rix-diagnostics-") as temporary:
        obj = Path(temporary) / "triangle.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        # Reports use the production importer but capture expected content errors.
        valid = diagnose_asset(obj)
        missing = diagnose_asset(Path(temporary) / "missing.glb")
        print(f"asset: ok={valid.ok} kind={valid.kind} {valid.summary}")
        print(
            f"asset: ok={missing.ok} type={missing.error_type} "
            f"message={missing.error_message}"
        )

        game = Game("RIX — diagnostics", (960, 540), vsync=True)
        scene = Scene("diagnostics example")
        with scene:
            Light("ambient", intensity=0.3)
            Light("directional", rotation=(-35, -30, 0))
            Plane(size=(12, 12), color=(0.12, 0.16, 0.22))
            Cube(position=(0, 0.5, 0), color=(0.12, 0.65, 0.95))
        # The overlay is a normal scene entity and two retained native HUD items.
        DebugOverlay(game, scene=scene)
        game.load_scene(scene)
        if seconds is not None:
            threading.Thread(
                target=lambda: (time.sleep(seconds), game.stop()), daemon=True
            ).start()
        game.run()
        print(
            "diagnostics_example: PASS "
            f"frames={game.frame_count} entities={scene.entity_count}"
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
