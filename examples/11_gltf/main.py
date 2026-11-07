"""RIX glTF 2.0 base-pose rendering and skeletal clip sampling example."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import tempfile
import threading
import time

from rix import Camera, Entity, Game, Light, Model, Plane, Scene, load_gltf


def _write_asset(directory: Path) -> Path:
    binary = struct.pack(
        "<18f3Hxx32f2f6f",
        *(
            (0, 0, 0, 1.5, 0, 0, 0, 1.5, 0)
            + (0, 0, 1) * 3
            + (0, 1, 2)
            + (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) * 2
            + (0, 2)
            + (-0.6, 1, 0, 0.6, 1.8, 0)
        ),
    )
    (directory / "sample.bin").write_bytes(binary)
    document = {
        "asset": {"version": "2.0", "generator": "RIX example"},
        "buffers": [{"uri": "sample.bin", "byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            {"buffer": 0, "byteOffset": 72, "byteLength": 6},
            {"buffer": 0, "byteOffset": 80, "byteLength": 128},
            {"buffer": 0, "byteOffset": 208, "byteLength": 8},
            {"buffer": 0, "byteOffset": 216, "byteLength": 24},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1.5, 1.5, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 3, "componentType": 5126, "count": 2, "type": "MAT4"},
            {
                "bufferView": 4,
                "componentType": 5126,
                "count": 2,
                "type": "SCALAR",
                "min": [0],
                "max": [2],
            },
            {"bufferView": 5, "componentType": 5126, "count": 2, "type": "VEC3"},
        ],
        "materials": [
            {
                "name": "Imported PBR",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.15, 0.55, 0.95, 1],
                    "metallicFactor": 0.35,
                    "roughnessFactor": 0.3,
                },
            }
        ],
        "meshes": [
            {
                "name": "Triangle",
                "primitives": [
                    {"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}
                ],
            }
        ],
        "nodes": [
            {"name": "Mesh", "mesh": 0, "skin": 0, "children": [1]},
            {"name": "Root", "children": [2]},
            {"name": "Tip", "translation": [0, 1, 0]},
        ],
        "skins": [
            {"name": "Rig", "joints": [1, 2], "skeleton": 1, "inverseBindMatrices": 3}
        ],
        "animations": [
            {
                "name": "Wave",
                "samplers": [{"input": 4, "output": 5, "interpolation": "LINEAR"}],
                "channels": [
                    {"sampler": 0, "target": {"node": 2, "path": "translation"}}
                ],
            }
        ],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    path = directory / "sample.gltf"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def run(*, seconds: float | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rix-gltf-") as temporary:
        path = _write_asset(Path(temporary))
        imported = load_gltf(path)
        if imported.skeleton is None or not imported.animations:
            raise RuntimeError("generated glTF did not import its skeleton and clip")

        scene = Scene("glTF example")
        camera = Camera(position=(3, 2.5, 6))
        camera.look_at((0.5, 0.5, 0))
        scene.camera = camera
        with scene:
            Light("ambient", intensity=0.28)
            Light("directional", rotation=(-30, -35, 0))
            Plane(position=(0.5, -0.3, 0), size=(6, 5), color=(0.16, 0.19, 0.25))
            Model(path, position=(0, 0, 0))

        status = scene.hud.text("glTF base pose", position=(22, 22), font_size=22)
        clip = imported.animations[0]
        skeleton = imported.skeleton

        class ClipSampler(Entity):
            def __init__(self) -> None:
                super().__init__("clip sampler")
                self.elapsed = 0.0

            def update(self, delta_seconds: float) -> None:
                self.elapsed += delta_seconds
                pose = clip.sample(skeleton, self.elapsed)
                tip = pose[1].position
                status.text = (
                    f"glTF base pose | Wave sample: ({tip.x:.2f}, {tip.y:.2f})"
                )

        with scene:
            ClipSampler()

        game = Game("RIX — glTF 2.0", (960, 540), vsync=True)
        game.load_scene(scene)
        if seconds is not None:
            threading.Thread(
                target=lambda: (time.sleep(seconds), game.stop()), daemon=True
            ).start()
        game.run()
        print(
            "gltf_example: PASS "
            f"frames={game.frame_count} triangles={imported.triangle_count} "
            f"joints={len(skeleton.joints)} clips={len(imported.animations)}"
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
