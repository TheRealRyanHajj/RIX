from __future__ import annotations

import json
from pathlib import Path
import struct

import pytest

from rix import (
    AssetError,
    Collider,
    GltfInfo,
    MeshRenderer,
    MissingAssetError,
    Model,
    ModelCache,
    Scene,
    load_gltf,
)


def _asset(path: Path) -> Path:
    binary = struct.pack(
        "<9f9f6f3Hxx32f2f6f",
        *(
            (0, 0, 0, 1, 0, 0, 0, 1, 0)
            + (0, 0, 1, 0, 0, 1, 0, 0, 1)
            + (0, 0, 1, 0, 0, 1)
            + (0, 1, 2)
            + (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) * 2
            + (0, 1)
            + (0, 1, 0, 1, 2, 0)
        ),
    )
    (path / "asset.bin").write_bytes(binary)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "asset.bin", "byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            {"buffer": 0, "byteOffset": 72, "byteLength": 24},
            {"buffer": 0, "byteOffset": 96, "byteLength": 6},
            {"buffer": 0, "byteOffset": 104, "byteLength": 128},
            {"buffer": 0, "byteOffset": 232, "byteLength": 8},
            {"buffer": 0, "byteOffset": 240, "byteLength": 24},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "min": [0, 0, 0],
                "max": [1, 1, 0],
            },
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
            {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 4, "componentType": 5126, "count": 2, "type": "MAT4"},
            {
                "bufferView": 5,
                "componentType": 5126,
                "count": 2,
                "type": "SCALAR",
                "min": [0],
                "max": [1],
            },
            {"bufferView": 6, "componentType": 5126, "count": 2, "type": "VEC3"},
        ],
        "materials": [
            {
                "name": "Copper",
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.8, 0.2, 0.1, 1],
                    "metallicFactor": 0.3,
                    "roughnessFactor": 0.7,
                },
            }
        ],
        "meshes": [
            {
                "name": "Triangle",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ],
            }
        ],
        "nodes": [
            {"name": "MeshNode", "mesh": 0, "skin": 0, "children": [1]},
            {"name": "Root", "children": [2]},
            {"name": "Tip", "translation": [0, 1, 0]},
        ],
        "skins": [
            {
                "name": "Rig",
                "joints": [1, 2],
                "skeleton": 1,
                "inverseBindMatrices": 4,
            }
        ],
        "animations": [
            {
                "name": "Wave",
                "samplers": [{"input": 5, "output": 6, "interpolation": "LINEAR"}],
                "channels": [
                    {"sampler": 0, "target": {"node": 2, "path": "translation"}}
                ],
            }
        ],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    source = path / "asset.gltf"
    source.write_text(json.dumps(document), encoding="utf-8")
    return source


def test_load_gltf_skeleton_clip_sample_and_model_dispatch(tmp_path: Path) -> None:
    path = _asset(tmp_path)
    info = load_gltf(path)
    assert isinstance(info, GltfInfo)
    assert info.triangle_count == 1
    assert info.parts[0].vertex_count == 3
    assert info.materials[1].metallic == pytest.approx(0.3)
    assert info.materials[1].roughness == pytest.approx(0.7)
    assert info.materials[1].double_sided is True
    assert info.skeleton is not None
    assert [joint.parent for joint in info.skeleton.joints] == [None, 0]
    assert len(info.animations) == 1
    pose = info.animations[0].sample(info.skeleton, 0.5, loop=False)
    assert tuple(pose[1].position) == pytest.approx((0.5, 1.5, 0.0))
    assert tuple(info.animations[0].sample(info.skeleton, 1.5)[1].position) == pytest.approx(
        tuple(pose[1].position)
    )

    scene = Scene("glTF")
    model = Model(path, scene=scene, collider="mesh")
    renderer = model.get_component(MeshRenderer)
    collider = model.get_component(Collider)
    assert renderer is not None and renderer.asset == path.resolve()
    assert collider is not None and collider.shape == "mesh"

    cache = ModelCache()
    assert cache.load(path).triangle_count == 1
    assert len(cache) == 1


def test_gltf_diagnostics_and_sampling_validation(tmp_path: Path) -> None:
    path = _asset(tmp_path)
    info = load_gltf(path)
    assert info.skeleton is not None
    with pytest.raises(ValueError, match="non-negative"):
        info.animations[0].sample(info.skeleton, -1)
    with pytest.raises(TypeError, match="loop"):
        info.animations[0].sample(info.skeleton, 0, loop=1)  # type: ignore[arg-type]

    (tmp_path / "asset.bin").unlink()
    with pytest.raises(MissingAssetError, match="external buffer"):
        load_gltf(path)

    document = json.loads(path.read_text(encoding="utf-8"))
    document["extensionsRequired"] = ["KHR_draco_mesh_compression"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(AssetError, match="required extensions"):
        load_gltf(path)
