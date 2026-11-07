"""Real D3D11 check that scene cleanup releases shared GPU textures."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import rix as e3


def main() -> None:
    with TemporaryDirectory(prefix="rix_gpu_lifetime_") as temporary:
        root = Path(temporary)
        game = e3.Game(
            "RIX AutoTexture GPU lifetime",
            resolution=(640, 360),
            vsync=False,
            graphics_preset="low",
        )
        try:
            game.tick(0)
            baseline_count = game.renderer_stats.texture_count
            baseline_bytes = game.renderer_stats.texture_memory_bytes

            for index in range(6):
                e3.Cube(
                    position=((index - 2.5) * 0.3, 0, 0),
                    texture=root / f"unique_{index}.png",
                )
            (root / "model.mtl").write_text(
                "newmtl Surface\nmap_Kd model.png\n", encoding="utf-8"
            )
            (root / "model.obj").write_text(
                "mtllib model.mtl\n"
                "v -1 0 0\nv 1 0 0\nv 0 2 0\n"
                "vt 0 0\nvt 1 0\nvt 0.5 1\n"
                "usemtl Surface\nf 1/1 2/2 3/3\n",
                encoding="utf-8",
            )
            e3.Model(root / "model.obj")
            for _ in range(3):
                game.tick(0)
            loaded_count = game.renderer_stats.texture_count
            loaded_bytes = game.renderer_stats.texture_memory_bytes
            if loaded_count < baseline_count + 14 or loaded_bytes <= baseline_bytes:
                raise AssertionError(
                    "primitive/model albedo and normal textures were not uploaded to D3D11"
                )

            assert game.scene is not None
            game.scene.clear()
            for _ in range(3):
                game.tick(0)
            released_count = game.renderer_stats.texture_count
            released_bytes = game.renderer_stats.texture_memory_bytes
            if released_count != baseline_count or released_bytes != baseline_bytes:
                raise AssertionError(
                    "scene cleanup retained GPU textures: "
                    f"baseline={baseline_count}/{baseline_bytes}, "
                    f"loaded={loaded_count}/{loaded_bytes}, "
                    f"released={released_count}/{released_bytes}"
                )

            print(
                "autotexture_gpu_lifetime: PASS "
                f"baseline={baseline_count}/{baseline_bytes} "
                f"loaded={loaded_count}/{loaded_bytes} "
                f"released={released_count}/{released_bytes}"
            )
        finally:
            if game.running:
                game.stop()
                game.tick(0)
            game.close()


if __name__ == "__main__":
    main()
