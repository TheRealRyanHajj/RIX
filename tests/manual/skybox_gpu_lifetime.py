"""Bounded D3D11 check for panorama/cubemap replacement and GPU cleanup."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import rix as e3


def pump(game: e3.Game, frames: int = 4) -> e3.RendererStats:
    for _ in range(frames):
        game.tick()
    return game.renderer_stats


def main() -> None:
    game = e3.Game(
        "RIX skybox GPU lifetime", (800, 450), graphics_preset="low",
        auto_setup=False,
    )
    game.load_scene(e3.Scene("sky lifetime"))
    try:
        baseline = pump(game)
        with TemporaryDirectory(prefix="rix-sky-") as temporary:
            root = Path(temporary)
            game.skybox = root / "panorama.png"
            panorama = pump(game)
            game.skybox = e3.Skybox(cubemap=root / "cubemap")
            cubemap = pump(game)
            game.skybox = None
            released = pump(game)

        if panorama.texture_count != baseline.texture_count + 1:
            raise RuntimeError("panorama did not allocate exactly one retained GPU texture")
        if cubemap.texture_count != baseline.texture_count + 1:
            raise RuntimeError("cubemap replacement retained a stale panorama texture")
        if released.texture_count != baseline.texture_count:
            raise RuntimeError("disabling the sky retained a GPU sky texture")
        if released.texture_memory_bytes != baseline.texture_memory_bytes:
            raise RuntimeError("sky replacement did not return texture memory to baseline")
        print(
            "skybox_gpu_lifetime: PASS "
            f"baseline={baseline.texture_count}/{baseline.texture_memory_bytes} "
            f"panorama={panorama.texture_count}/{panorama.texture_memory_bytes} "
            f"cubemap={cubemap.texture_count}/{cubemap.texture_memory_bytes} "
            f"released={released.texture_count}/{released.texture_memory_bytes}"
        )
    finally:
        game.close()


if __name__ == "__main__":
    main()
