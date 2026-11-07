from __future__ import annotations

import base64
from pathlib import Path

import pytest

from rix import DebugOverlay, Game, Scene, diagnose_asset


_PNG_2X2 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAAXNSR0IArs4c6QAAAARn"
    "QU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAXSURBVBhXY/jPwPCfoYHh"
    "PwMDw38wAABD1Al4TlSdlQAAAABJRU5ErkJggg=="
)


def test_structured_asset_diagnostics(tmp_path: Path) -> None:
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(base64.b64decode(_PNG_2X2))
    image = diagnose_asset(image_path)
    assert image.ok
    assert image.kind == "image"
    assert (image.width, image.height) == (2, 2)
    assert image.error_message is None

    obj_path = tmp_path / "triangle.obj"
    obj_path.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    model = diagnose_asset(obj_path)
    assert model.ok
    assert model.kind == "obj"
    assert (model.triangle_count, model.part_count) == (1, 1)

    missing = diagnose_asset(tmp_path / "missing.gltf")
    assert not missing.ok
    assert missing.kind == "gltf"
    assert missing.error_type == "MissingAssetError"
    assert "missing.gltf" in (missing.error_message or "")

    unsupported = diagnose_asset(tmp_path / "mesh.fbx")
    assert not unsupported.ok
    assert unsupported.kind == "unknown"
    assert unsupported.error_type == "AssetError"
    with pytest.raises(TypeError, match="path"):
        diagnose_asset(42)  # type: ignore[arg-type]


def test_debug_overlay_uses_native_hud_and_live_stats() -> None:
    game = Game("diagnostics")
    scene = Scene("diagnostics")
    overlay = DebugOverlay(game, scene=scene, refresh_interval=0.1)

    assert scene.entity_count == 1
    assert len(scene.hud.elements) == 2
    overlay.update(0.05)
    assert "FPS" in overlay.text.text
    assert "entities 1" in overlay.text.text
    assert "features baseline" in overlay.text.text

    overlay.hide()
    assert not overlay.panel.visible
    assert not overlay.text.visible
    overlay.show()
    assert overlay.panel.visible
    assert overlay.text.visible

    with pytest.raises(ValueError, match="refresh_interval"):
        DebugOverlay(game, scene=Scene("invalid"), refresh_interval=0)
