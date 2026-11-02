from __future__ import annotations

import base64
from pathlib import Path

import pytest

from easy3d import Button, Panel, Scene, Text


_PNG_2X2 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAAXNSR0IArs4c6QAAAARn"
    "QU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAXSURBVBhXY/jPwPCfoYHh"
    "PwMDw38wAABD1Al4TlSdlQAAAABJRU5ErkJggg=="
)


def test_hud_retains_typed_panels_and_text() -> None:
    scene = Scene("hud")
    panel = scene.hud.panel(
        position=(-12, -12),
        size=(240, 96),
        anchor="bottom_right",
        color=(0.1, 0.2, 0.3, 0.8),
    )
    label = scene.hud.text(
        "Score: 3",
        position=(16, 16),
        font_size=28,
        z_index=2,
    )

    assert isinstance(panel, Panel)
    assert isinstance(label, Text)
    assert len(scene.hud.elements) == 2
    assert scene._native.ui_element_count == 2
    assert panel.anchor == "bottom_right"
    assert panel.size == (240, 96)
    assert label.text == "Score: 3"
    assert label.font_size == 28

    label.text = "Score: 4"
    label.color = (1, 0.8, 0.2, 1)
    panel.visible = False
    assert label.text == "Score: 4"
    assert label.color == pytest.approx((1, 0.8, 0.2, 1))
    assert not panel.visible


def test_stack_layout_respects_group_anchor() -> None:
    scene = Scene("layout")
    first = scene.hud.panel(size=(100, 30))
    second = scene.hud.panel(size=(50, 30))
    stack = scene.hud.stack(
        "horizontal", (first, second), anchor="bottom", position=(0, -20), spacing=10
    )

    assert first.anchor == second.anchor == "bottom"
    assert first.position == pytest.approx((-30, -20))
    assert second.position == pytest.approx((55, -20))

    second.size = (70, 30)
    stack.relayout()
    assert first.position == pytest.approx((-40, -20))
    assert second.position == pytest.approx((55, -20))


def test_topmost_enabled_button_clicks_once_per_press() -> None:
    scene = Scene("buttons")
    clicked: list[str] = []
    lower = scene.hud.button(
        "Lower", on_click=lambda _: clicked.append("lower"), size=(120, 40), z_index=1
    )
    upper = scene.hud.button(
        "Upper", on_click=lambda _: clicked.append("upper"), size=(120, 40), z_index=2
    )
    assert isinstance(lower, Button)
    assert isinstance(upper, Button)

    scene.hud._advance((320, 240), True, (640, 480))
    scene.hud._advance((320, 240), True, (640, 480))
    scene.hud._advance((320, 240), False, (640, 480))
    assert clicked == ["upper"]

    upper.enabled = False
    scene.hud._advance((320, 240), True, (640, 480))
    assert clicked == ["upper", "lower"]


def test_ui_lifecycle_and_validation(tmp_path: Path) -> None:
    scene = Scene("lifecycle")
    texture = tmp_path / "sprite.png"
    texture.write_bytes(base64.b64decode(_PNG_2X2))
    sprite = scene.hud.sprite(str(texture), size=(32, 32))
    assert Path(sprite.texture) == texture.resolve()
    panel = scene.hud.panel()
    panel.remove()
    panel.remove()
    assert panel not in scene.hud.elements
    with pytest.raises(ReferenceError):
        _ = panel.position

    with pytest.raises(ValueError, match="anchor"):
        scene.hud.panel(anchor="middle")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        scene.hud.panel(size=(0, 10))
    with pytest.raises(Exception, match="missing"):
        scene.hud.sprite(str(tmp_path / "missing.png"))

    label = scene.hud.text("clear me")
    scene.clear()
    assert label.removed
    assert scene.hud.elements == ()
    assert scene._native.ui_element_count == 0
