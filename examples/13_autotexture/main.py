"""Interactive visual validation scene for AutoTexture and material maps."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import struct
import threading
import time
import zlib

import rix as e3


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_swatch(path: Path, color: tuple[int, int, int, int], *, normal: bool = False) -> None:
    """Write one deterministic 16x16 test map without external image packages."""

    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    width = height = 16
    pixels = bytearray()
    for y in range(height):
        row = bytearray()
        for x in range(width):
            if normal:
                nx = 78 if (x // 4 + y // 4) % 2 else 178
                value = (nx, 128, 242, 255)
            else:
                shade = 35 if (x // 4 + y // 4) % 2 else 0
                value = tuple(min(255, channel + shade) for channel in color[:3]) + (color[3],)
            row.extend(value)
        pixels.extend(b"\0" + row)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(pixels), 9))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


class OrbitCamera(e3.Entity):
    def __init__(self, scene: e3.Scene) -> None:
        super().__init__("AutoTexture orbit camera", scene=scene)
        self.angle = 0.35

    def update(self, delta_seconds: float) -> None:
        self.angle += delta_seconds * 0.08
        camera = e3.Camera(
            position=(math.cos(self.angle) * 19, 9.5, math.sin(self.angle) * 19),
            vertical_fov_degrees=55,
        )
        camera.look_at((0, 1, 0))
        self.scene.camera = camera


def build_scene() -> e3.Scene:
    GENERATED.mkdir(parents=True, exist_ok=True)
    brick = GENERATED / "brick_wall.png"
    brick_normal = GENERATED / "brick_wall_normal.png"
    material = GENERATED / "material.png"
    rough = GENERATED / "material_roughness.png"
    metal = GENERATED / "material_metallic.png"
    _write_swatch(brick, (150, 55, 38, 255))
    _write_swatch(brick_normal, (128, 128, 255, 255), normal=True)
    _write_swatch(material, (120, 135, 150, 255))
    _write_swatch(rough, (45, 45, 45, 255))
    _write_swatch(metal, (230, 230, 230, 255))

    scene = e3.Scene("AutoTexture and advanced materials")
    camera = e3.Camera(position=(18, 9.5, 8), vertical_fov_degrees=55)
    camera.look_at((0, 1, 0))
    scene.camera = camera
    with scene:
        OrbitCamera(scene)
        e3.Light("ambient", color=(0.42, 0.48, 0.62), intensity=0.22)
        e3.Light("directional", rotation=(-42, -28, 0), intensity=1.25)
        e3.Plane(
            position=(0, -0.55, 0),
            size=(24, 18),
            texture=GENERATED / "grass_tile.png",
            name="Large auto-tiled plane",
        )
        for index, size in enumerate((1.0, 2.0, 3.0)):
            e3.Cube(
                position=(-7 + index * 2.8, size * 0.5 - 0.5, 2.7),
                size=size,
                texture=GENERATED / "shared_tile.png",
                name=f"Shared tile cube {size:g}",
            )
        e3.Cube(
            position=(2.0, 1.0, 3.0),
            size=(2.5, 3.0, 1.5),
            texture=GENERATED / "six_face_atlas.png",
            texture_mode="atlas",
            name="Generated six-face atlas",
        )
        e3.Sphere(
            position=(6.2, 1.0, 2.8),
            radius=1.5,
            texture=GENERATED / "sphere.png",
            name="Spherical mapping",
        )
        e3.Cube(
            position=(-5.5, 1.0, -2.5),
            size=(3.0, 2.5, 0.45),
            texture=brick,
            normal_map=brick_normal,
            normal_strength=1.4,
            name="Normal-mapped wall",
        )
        e3.Cube(
            position=(-1.5, 0.75, -2.5),
            size=1.5,
            texture=material,
            roughness_map=rough,
            metallic_map=metal,
            name="Roughness and metallic maps",
        )
        e3.Model(ROOT / "assets" / "demo.obj", position=(2.0, -0.5, -3.0))
        e3.Model(ROOT / "assets" / "demo.gltf", position=(5.5, -0.5, -2.5))

    scene.hud.text(
        "AutoTexture: tiled density | atlas | sphere | OBJ | glTF | normal/PBR maps",
        position=(20, 18),
        font_size=20,
    )
    scene.hud.text(
        "Edit examples/13_autotexture/generated/*.png while running to test hot reload",
        position=(20, 48),
        font_size=16,
        color=(0.78, 0.86, 1.0, 1.0),
    )
    return scene


def run(seconds: float | None = None) -> None:
    game = e3.Game(
        "RIX — AutoTexture", (1280, 720), vsync=True, graphics_preset="high"
    )
    scene = build_scene()
    game.load_scene(scene)
    if seconds is not None:
        threading.Thread(
            target=lambda: (time.sleep(seconds), game.stop()), daemon=True
        ).start()
    game.run()
    stats = game.renderer_stats
    print(
        "autotexture_example: PASS "
        f"frames={game.frame_count} draw_calls={stats.draw_calls} "
        f"instanced={stats.instanced_draw_calls} cpu_ms={stats.cpu_frame_ms:.3f} "
        f"gpu_ms={stats.gpu_frame_ms:.3f} textures={stats.texture_count} "
        f"texture_bytes={stats.texture_memory_bytes}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=None)
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(arguments.seconds)


if __name__ == "__main__":
    main()
