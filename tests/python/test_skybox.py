from __future__ import annotations

from pathlib import Path
import struct
import zlib

import pytest

from rix import Scene, Skybox, load_image
from rix.autotexture import _png_bytes


def _generated_png_rows(path: Path) -> tuple[int, list[bytes]]:
    data = path.read_bytes()
    offset = 8
    compressed = bytearray()
    width = height = 0
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height = struct.unpack(">II", payload[:8])
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(compressed)
    stride = width * 4 + 1
    assert all(raw[row * stride] == 0 for row in range(height))
    return width, [raw[row * stride + 1 : (row + 1) * stride] for row in range(height)]


def test_procedural_skybox_is_scene_owned_mutable_and_disableable() -> None:
    first = Scene("first sky")
    second = Scene("second sky")
    assert first.skybox is not None
    assert first.skybox.kind == "procedural"
    first.skybox.top = "red"
    first.skybox.horizon = "orange"
    first.skybox.bottom = "black"
    first.skybox.brightness = 1.75
    first.skybox.rotation = 35
    info = first._native.skybox_info()
    assert info is not None
    assert info[0] == "procedural"
    assert info[1] == pytest.approx((1, 0, 0, 1))
    assert info[4:6] == pytest.approx((1.75, 35))
    assert second.skybox is not first.skybox

    first.skybox = None
    assert first.skybox is None
    assert first._native.skybox_info() is None
    first.skybox = "default"
    assert first.skybox is not None and first.skybox.kind == "procedural"


def test_missing_panorama_is_generated_once_and_native_validates_ratio(
    tmp_path: Path,
) -> None:
    path = tmp_path / "generated_sky.png"
    scene = Scene("panorama")
    scene.skybox = path
    assert path.is_file()
    assert path.with_suffix(".png.skybox.json").is_file()
    image = load_image(path)
    assert (image.width, image.height) == (2048, 1024)
    original = path.read_bytes()
    scene.skybox = path
    assert path.read_bytes() == original
    info = scene._native.skybox_info()
    assert info is not None and info[0] == "panorama"

    invalid = tmp_path / "square.png"
    invalid.write_bytes(_png_bytes(1, 1, bytes((255, 0, 0, 255))))
    with pytest.raises(ValueError, match="2:1"):
        scene.skybox = invalid


def test_cubemap_folder_generation_and_runtime_replacement(tmp_path: Path) -> None:
    folder = tmp_path / "cube"
    scene = Scene("cubemap")
    scene.skybox = Skybox(cubemap=folder, brightness=0.8, rotation=90)
    expected = ("right", "left", "top", "bottom", "back", "front")
    assert all((folder / f"{name}.png").is_file() for name in expected)
    assert scene.skybox is not None and scene.skybox.kind == "cubemap"
    info = scene._native.skybox_info()
    assert info is not None and info[0] == "cubemap"
    assert len(info[6]) == 6
    width, right_rows = _generated_png_rows(folder / "right.png")
    top_width, top_rows = _generated_png_rows(folder / "top.png")
    assert (width, top_width) == (512, 512)
    # The direction-derived starter gradient is continuous at this complete
    # side/top edge (not six unrelated flat face colors).
    assert right_rows[0] == top_rows[0]
    scene.skybox = Skybox(top="purple", bottom="black")
    assert scene.skybox.kind == "procedural"


def test_cubemap_generation_never_overwrites_existing_artwork(tmp_path: Path) -> None:
    folder = tmp_path / "authored"
    folder.mkdir()
    authored = folder / "right.png"
    authored.write_bytes(_png_bytes(1, 1, bytes((7, 8, 9, 255))))
    original = authored.read_bytes()
    sky = Skybox(cubemap=folder)
    assert sky.kind == "cubemap"
    assert authored.read_bytes() == original
    assert all((folder / f"{name}.png").is_file() for name in (
        "right", "left", "top", "bottom", "back", "front"
    ))
    with pytest.raises(ValueError, match="one size"):
        Scene("malformed authored cube").skybox = sky

    with pytest.raises(ValueError, match="missing faces"):
        Skybox(cubemap={"right": authored})
