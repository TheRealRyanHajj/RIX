"""D3D11 visual validation for back/front/none face-culling modes."""

from __future__ import annotations

import argparse
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


def _write_map(path: Path, *, normal: bool) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 32
    pixels = bytearray()
    for y in range(size):
        row = bytearray()
        for x in range(size):
            checker = (x // 4 + y // 4) % 2
            if normal:
                pixel = (168 if checker else 88, 128, 238, 255)
            else:
                pixel = (62, 126 + checker * 34, 188 + checker * 34, 255)
            row.extend(pixel)
        pixels.extend(b"\0" + row)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(pixels), 9))
        + _chunk(b"IEND", b"")
    )


def build_scene(view: str) -> e3.Scene:
    room_texture = GENERATED / "room.png"
    room_normal = GENERATED / "room_normal.png"
    _write_map(room_texture, normal=False)
    _write_map(room_normal, normal=True)

    scene = e3.Scene("Face culling")
    cameras = {
        "outside": ((13, 8, 16), (0, 1.5, 0)),
        "inside-double": ((-5, 2, 0), (-5, 2, -4)),
        "inside-front": ((5, 2, 0), (5, 2, -4)),
    }
    position, target = cameras[view]
    camera = e3.Camera(position=position, vertical_fov_degrees=62)
    camera.look_at(target)
    scene.camera = camera

    with scene:
        e3.Light("ambient", color=(0.35, 0.42, 0.55), intensity=0.38)
        e3.Light("directional", rotation=(-35, -30, 0), intensity=1.3)
        e3.Plane(size=(24, 14), y=-1.05, color=(0.24, 0.27, 0.31, 1), collider=False)
        e3.Cube(
            position=(-5, 2, 0),
            size=(6, 6, 6),
            texture=room_texture,
            normal_map=room_normal,
            normal_strength=1.2,
            roughness=0.72,
            metallic=0.18,
            double_sided=True,
            collider=False,
            name="Double-sided normal-mapped room",
        )
        e3.Cube(
            position=(5, 2, 0),
            size=(6, 6, 6),
            color=(0.92, 0.48, 0.22, 1),
            cull_mode="front",
            collider=False,
            name="Interior-only room",
        )
        e3.Cube(
            position=(0, 0, 4),
            size=2,
            color="purple",
            collider=False,
            name="Ordinary outward cube",
        )
        e3.Plane(
            position=(0, 1.5, 0),
            rotation=(90, 0, 0),
            size=(4, 3),
            color=(0.25, 0.9, 0.65, 1),
            lit=False,
            double_sided=True,
            collider=False,
            name="Double-sided plane",
        )

    scene.hud.text(
        f"Face culling view: {view} | blue=double-sided | orange=front-cull",
        position=(20, 18),
        font_size=20,
    )
    scene.hud.text(
        "Depth testing remains enabled; culling changes visibility only.",
        position=(20, 48),
        font_size=16,
        color=(0.8, 0.88, 1.0, 1.0),
    )
    return scene


def run(view: str, seconds: float | None) -> None:
    game = e3.Game(
        "RIX — Face Culling",
        (1280, 720),
        vsync=True,
        graphics_preset="high",
        auto_setup=False,
    )
    game.load_scene(build_scene(view))
    if seconds is not None:
        threading.Thread(
            target=lambda: (time.sleep(seconds), game.stop()), daemon=True
        ).start()
    game.run()
    stats = game.renderer_stats
    print(
        "face_culling_example: PASS "
        f"view={view} frames={game.frame_count} draw_calls={stats.draw_calls} "
        f"instanced={stats.instanced_draw_calls} gpu_ms={stats.gpu_frame_ms:.3f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--view",
        choices=("outside", "inside-double", "inside-front"),
        default="outside",
    )
    parser.add_argument("--seconds", type=float, default=None)
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(arguments.view, arguments.seconds)


if __name__ == "__main__":
    main()
