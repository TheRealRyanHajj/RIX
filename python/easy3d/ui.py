"""Native-rendered 2D HUD elements and lightweight button interaction."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Literal, TYPE_CHECKING

from .components import ColorValue, normalize_color

if TYPE_CHECKING:
    from .scene import Scene


Anchor = Literal[
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
]
StackDirection = Literal["horizontal", "vertical"]

_ANCHORS: tuple[Anchor, ...] = (
    "top_left",
    "top",
    "top_right",
    "left",
    "center",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
)


def _pair(value: tuple[float, float], label: str, *, positive: bool = False) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{label} must be a two-number tuple")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise TypeError(f"{label} must be a two-number tuple")
    result = (float(value[0]), float(value[1]))
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} values must be finite")
    if positive and not all(item > 0 for item in result):
        raise ValueError(f"{label} values must be positive")
    return result


def _anchor(value: Anchor) -> Anchor:
    if value not in _ANCHORS:
        raise ValueError(f"anchor must be one of {', '.join(_ANCHORS)}")
    return value


def _anchor_factor(anchor: Anchor) -> tuple[float, float]:
    horizontal = 0.0 if anchor.endswith("left") or anchor == "left" else 1.0 if anchor.endswith("right") or anchor == "right" else 0.5
    vertical = 0.0 if anchor.startswith("top") else 1.0 if anchor.startswith("bottom") else 0.5
    return horizontal, vertical


def _text_size(text: str, font_size: float) -> tuple[float, float]:
    lines = text.splitlines() or [""]
    return (
        max(1.0, max(len(line) for line in lines) * font_size * 0.6),
        max(1.0, len(lines) * font_size * 1.25),
    )


class UIElement:
    """One retained HUD item rendered natively above the 3D/postprocess passes."""

    __slots__ = ("_scene", "_id", "_removed")

    def __init__(self, scene: Scene, element_id: int) -> None:
        self._scene = scene
        self._id = int(element_id)
        self._removed = False

    @property
    def id(self) -> int:
        return self._id

    @property
    def removed(self) -> bool:
        return self._removed

    def _info(self) -> tuple[object, ...]:
        if self._removed:
            raise ReferenceError("UI element has been removed")
        return self._scene._native.ui_element_info(self._id)

    def _update(self, **changes: object) -> None:
        info = self._info()
        self._scene._require_mutable()
        values = {
            "anchor": info[1],
            "position": info[2],
            "size": info[3],
            "color": info[4],
            "text": info[5],
            "text_color": info[6],
            "font_size": info[7],
            "z_index": info[8],
            "visible": info[9],
            "enabled": info[10],
        }
        values.update(changes)
        self._scene._native.update_ui_element(self._id, **values)

    @property
    def kind(self) -> str:
        return str(self._info()[0])

    @property
    def anchor(self) -> Anchor:
        return self._info()[1]  # type: ignore[return-value]

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self._update(anchor=_anchor(value))

    @property
    def position(self) -> tuple[float, float]:
        return tuple(self._info()[2])  # type: ignore[arg-type,return-value]

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        self._update(position=_pair(value, "position"))

    @property
    def size(self) -> tuple[float, float]:
        return tuple(self._info()[3])  # type: ignore[arg-type,return-value]

    @size.setter
    def size(self, value: tuple[float, float]) -> None:
        self._update(size=_pair(value, "size", positive=True))

    @property
    def color(self) -> tuple[float, float, float, float]:
        return tuple(self._info()[4])  # type: ignore[arg-type,return-value]

    @color.setter
    def color(self, value: ColorValue) -> None:
        self._update(color=normalize_color(value))

    @property
    def text(self) -> str:
        return str(self._info()[5])

    @text.setter
    def text(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("text must be a non-empty string")
        self._update(text=value)

    @property
    def text_color(self) -> tuple[float, float, float, float]:
        return tuple(self._info()[6])  # type: ignore[arg-type,return-value]

    @text_color.setter
    def text_color(self, value: ColorValue) -> None:
        self._update(text_color=normalize_color(value))

    @property
    def font_size(self) -> float:
        return float(self._info()[7])

    @font_size.setter
    def font_size(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("font_size must be a number")
        self._update(font_size=float(value))

    @property
    def z_index(self) -> int:
        return int(self._info()[8])

    @z_index.setter
    def z_index(self, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("z_index must be an integer")
        self._update(z_index=value)

    @property
    def visible(self) -> bool:
        return bool(self._info()[9])

    @visible.setter
    def visible(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("visible must be a bool")
        self._update(visible=value)

    @property
    def enabled(self) -> bool:
        return bool(self._info()[10])

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("enabled must be a bool")
        self._update(enabled=value)

    def remove(self) -> None:
        if self._removed:
            return
        self._scene._require_mutable()
        self._scene._native.remove_ui_element(self._id)
        self._removed = True
        self._scene.hud._elements.pop(self._id, None)

    def _rect(self, viewport: tuple[int, int]) -> tuple[float, float, float, float]:
        width, height = self.size
        x_factor, y_factor = _anchor_factor(self.anchor)
        x = viewport[0] * x_factor + self.position[0] - width * x_factor
        y = viewport[1] * y_factor + self.position[1] - height * y_factor
        return x, y, width, height


class Panel(UIElement):
    pass


class Sprite(UIElement):
    @property
    def texture(self) -> str:
        return str(self._info()[11])


class Text(UIElement):
    @property
    def text(self) -> str:
        return super().text

    @text.setter
    def text(self, value: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError("text must be a non-empty string")
        self._update(text=value, size=_text_size(value, self.font_size))

    @property
    def font_size(self) -> float:
        return super().font_size

    @font_size.setter
    def font_size(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("font_size must be a number")
        size = float(value)
        self._update(font_size=size, size=_text_size(self.text, size))

    @property
    def color(self) -> tuple[float, float, float, float]:
        return self.text_color

    @color.setter
    def color(self, value: ColorValue) -> None:
        self.text_color = value


class Button(UIElement):
    __slots__ = ("on_click", "normal_color", "hover_color", "pressed_color", "_state")

    def __init__(
        self,
        scene: Scene,
        element_id: int,
        on_click: Callable[[Button], None] | None,
        normal_color: tuple[float, float, float, float],
        hover_color: tuple[float, float, float, float],
        pressed_color: tuple[float, float, float, float],
    ) -> None:
        super().__init__(scene, element_id)
        if on_click is not None and not callable(on_click):
            raise TypeError("on_click must be callable or None")
        self.on_click = on_click
        self.normal_color = normal_color
        self.hover_color = hover_color
        self.pressed_color = pressed_color
        self._state = "normal"

    def _set_pointer_state(self, hovered: bool, pressed: bool) -> None:
        state = "pressed" if hovered and pressed else "hover" if hovered else "normal"
        if state == self._state:
            return
        self._state = state
        self.color = (
            self.pressed_color if state == "pressed"
            else self.hover_color if state == "hover"
            else self.normal_color
        )


class Stack:
    """A small retained horizontal or vertical layout group."""

    __slots__ = ("direction", "anchor", "position", "spacing", "elements")

    def __init__(
        self,
        direction: StackDirection,
        *,
        anchor: Anchor,
        position: tuple[float, float],
        spacing: float,
    ) -> None:
        if direction not in ("horizontal", "vertical"):
            raise ValueError("stack direction must be 'horizontal' or 'vertical'")
        if not math.isfinite(spacing) or spacing < 0:
            raise ValueError("stack spacing must be finite and non-negative")
        self.direction = direction
        self.anchor = _anchor(anchor)
        self.position = _pair(position, "position")
        self.spacing = float(spacing)
        self.elements: list[UIElement] = []

    def add(self, *elements: UIElement) -> Stack:
        self.elements.extend(elements)
        self.relayout()
        return self

    def relayout(self) -> None:
        live = [element for element in self.elements if not element.removed]
        if not live:
            return
        factor_x, factor_y = _anchor_factor(self.anchor)
        sizes = [element.size for element in live]
        if self.direction == "horizontal":
            total = sum(size[0] for size in sizes) + self.spacing * (len(live) - 1)
            cursor = -total * factor_x
            for element, size in zip(live, sizes, strict=True):
                element.anchor = self.anchor
                element.position = (
                    self.position[0] + cursor + size[0] * factor_x,
                    self.position[1],
                )
                cursor += size[0] + self.spacing
        else:
            total = sum(size[1] for size in sizes) + self.spacing * (len(live) - 1)
            cursor = -total * factor_y
            for element, size in zip(live, sizes, strict=True):
                element.anchor = self.anchor
                element.position = (
                    self.position[0],
                    self.position[1] + cursor + size[1] * factor_y,
                )
                cursor += size[1] + self.spacing


class HUD:
    """Retained overlay owned by one Scene."""

    __slots__ = ("_scene", "_elements", "_mouse_was_down")

    def __init__(self, scene: Scene) -> None:
        self._scene = scene
        self._elements: dict[int, UIElement] = {}
        self._mouse_was_down = False

    @property
    def elements(self) -> tuple[UIElement, ...]:
        return tuple(item for item in self._elements.values() if not item.removed)

    def _add(
        self,
        cls: type[UIElement],
        kind: str,
        *,
        position: tuple[float, float],
        size: tuple[float, float],
        anchor: Anchor,
        color: ColorValue,
        text: str = "",
        text_color: ColorValue = (1, 1, 1, 1),
        font_size: float = 24,
        z_index: int = 0,
        texture: str | None = None,
    ) -> UIElement:
        self._scene._require_mutable()
        element_id = self._scene._native.add_ui_element(
            kind,
            _anchor(anchor),
            _pair(position, "position"),
            _pair(size, "size", positive=kind != "text"),
            normalize_color(color),
            text,
            normalize_color(text_color),
            float(font_size),
            z_index,
            True,
            True,
            texture,
        )
        element = cls(self._scene, element_id)
        self._elements[element_id] = element
        return element

    def panel(
        self,
        *,
        position: tuple[float, float] = (0, 0),
        size: tuple[float, float] = (200, 100),
        anchor: Anchor = "top_left",
        color: ColorValue = (0.08, 0.1, 0.14, 0.85),
        z_index: int = 0,
    ) -> Panel:
        return self._add(Panel, "panel", position=position, size=size, anchor=anchor, color=color, z_index=z_index)  # type: ignore[return-value]

    def sprite(
        self,
        texture: str,
        *,
        position: tuple[float, float] = (0, 0),
        size: tuple[float, float] = (64, 64),
        anchor: Anchor = "top_left",
        color: ColorValue = (1, 1, 1, 1),
        z_index: int = 0,
    ) -> Sprite:
        if not isinstance(texture, str) or not texture:
            raise ValueError("texture must be a non-empty path string")
        return self._add(Sprite, "sprite", position=position, size=size, anchor=anchor, color=color, z_index=z_index, texture=texture)  # type: ignore[return-value]

    def text(
        self,
        text: str,
        *,
        position: tuple[float, float] = (0, 0),
        anchor: Anchor = "top_left",
        color: ColorValue = (1, 1, 1, 1),
        font_size: float = 24,
        z_index: int = 0,
    ) -> Text:
        if not isinstance(text, str) or not text:
            raise ValueError("text must be a non-empty string")
        measured = _text_size(text, float(font_size))
        return self._add(Text, "text", position=position, size=measured, anchor=anchor, color=(1, 1, 1, 0), text=text, text_color=color, font_size=font_size, z_index=z_index)  # type: ignore[return-value]

    def button(
        self,
        text: str,
        *,
        on_click: Callable[[Button], None] | None = None,
        position: tuple[float, float] = (0, 0),
        size: tuple[float, float] = (180, 48),
        anchor: Anchor = "center",
        color: ColorValue = (0.15, 0.32, 0.55, 0.96),
        hover_color: ColorValue = (0.2, 0.45, 0.75, 0.98),
        pressed_color: ColorValue = (0.1, 0.24, 0.42, 1),
        text_color: ColorValue = (1, 1, 1, 1),
        font_size: float = 22,
        z_index: int = 0,
    ) -> Button:
        normal = normalize_color(color)
        hover = normalize_color(hover_color)
        pressed = normalize_color(pressed_color)
        base = self._add(UIElement, "button", position=position, size=size, anchor=anchor, color=normal, text=text, text_color=text_color, font_size=font_size, z_index=z_index)
        button = Button(self._scene, base.id, on_click, normal, hover, pressed)
        self._elements[base.id] = button
        return button

    def stack(
        self,
        direction: StackDirection,
        elements: Iterable[UIElement] = (),
        *,
        position: tuple[float, float] = (0, 0),
        anchor: Anchor = "center",
        spacing: float = 8,
    ) -> Stack:
        stack = Stack(direction, anchor=anchor, position=position, spacing=spacing)
        stack.add(*tuple(elements))
        return stack

    def clear(self) -> None:
        self._scene._require_mutable()
        self._scene._native.clear_ui()
        for element in self._elements.values():
            element._removed = True
        self._elements.clear()
        self._mouse_was_down = False

    def _native_cleared(self) -> None:
        for element in self._elements.values():
            element._removed = True
        self._elements.clear()
        self._mouse_was_down = False

    def _advance(
        self,
        pointer: tuple[float, float],
        mouse_down: bool,
        viewport: tuple[int, int],
    ) -> None:
        all_buttons = [item for item in self.elements if isinstance(item, Button)]
        buttons = sorted(
            (item for item in all_buttons if item.enabled and item.visible),
            key=lambda item: (item.z_index, item.id),
            reverse=True,
        )
        hovered: Button | None = None
        for button in buttons:
            x, y, width, height = button._rect(viewport)
            if x <= pointer[0] <= x + width and y <= pointer[1] <= y + height:
                hovered = button
                break
        for button in all_buttons:
            button._set_pointer_state(button is hovered, mouse_down)
        clicked = mouse_down and not self._mouse_was_down
        self._mouse_was_down = mouse_down
        if clicked and hovered is not None and hovered.on_click is not None:
            hovered.on_click(hovered)
