from __future__ import annotations

from pathlib import Path

import pytest

from easy3d import AssetError, MissingAssetError
from easy3d.assets import ModelCache, load_obj


def _write_model(tmp_path: Path) -> Path:
    (tmp_path / "albedo.png").write_bytes(b"path validation fixture")
    (tmp_path / "quad.mtl").write_text(
        "newmtl Surface\nKd 0.25 0.5 0.75\nd 0.8\nmap_Kd albedo.png\n",
        encoding="utf-8",
    )
    model = tmp_path / "quad.obj"
    model.write_text(
        "mtllib quad.mtl\n"
        "o Quad\n"
        "v -1 0 0\nv 1 0 0\nv 1 2 0\nv -1 2 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n"
        "vn 0 0 1\n"
        "usemtl Surface\n"
        "f 1/1/1 2/2/1 3/3/1 4/4/1\n",
        encoding="utf-8",
    )
    return model


def test_obj_material_metadata_and_cache(tmp_path: Path) -> None:
    path = _write_model(tmp_path)
    model = load_obj(path)

    assert model.path == path.resolve()
    assert model.triangle_count == 2
    assert len(model.parts) == 1
    assert model.parts[0].vertex_count == 4
    assert model.parts[0].index_count == 6
    assert model.parts[0].material_index == 1
    assert model.materials[1].name == "Surface"
    assert model.materials[1].diffuse_color == pytest.approx((0.25, 0.5, 0.75, 0.8))
    assert model.materials[1].diffuse_texture == (tmp_path / "albedo.png").resolve()

    cache = ModelCache()
    cache.load(path)
    cache.load(tmp_path / "." / "quad.obj")
    assert len(cache) == 1
    cache.clear()
    assert len(cache) == 0


def test_obj_errors_are_actionable(tmp_path: Path) -> None:
    with pytest.raises(MissingAssetError, match="missing.obj"):
        load_obj(tmp_path / "missing.obj")

    malformed = tmp_path / "malformed.obj"
    malformed.write_text("v 0 0 0\nv 1 0 0\nf 1 2 99\n", encoding="utf-8")
    with pytest.raises(AssetError, match="failed to parse OBJ|out-of-range"):
        load_obj(malformed)

    unsupported = tmp_path / "mesh.gltf"
    unsupported.write_text("{}", encoding="utf-8")
    with pytest.raises(AssetError, match="unsupported model format"):
        load_obj(unsupported)
