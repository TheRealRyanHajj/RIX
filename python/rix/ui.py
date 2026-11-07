"""Native-rendered 2D HUD elements and lightweight button interaction."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from contextvars import ContextVar, Token
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
Alignment = Literal["start", "center", "end"]

_current_layout: ContextVar[object | None] = ContextVar(
    "rix_current_ui_layout", default=None
)

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


def _space(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _adopt(item: object) -> object:
    layout = _current_layout.get()
    if layout is not None:
        layout.add(item)  # type: ignore[attr-defined]
    return item


def _item_size(item: object) -> tuple[float, float]:
    size = getattr(item, "size", None)
    if not isinstance(size, tuple) or len(size) != 2:
        raise TypeError("layout children must be UI elements or layout groups")
    return float(size[0]), float(size[1])


def _place(
    item: object,
    anchor: Anchor,
    position: tuple[float, float],
) -> None:
    setattr(item, "anchor", anchor)
    setattr(item, "position", position)
    relayout = getattr(item, "relayout", None)
    if callable(relayout):
        relayout()


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
    def __new__(cls, *args: object, **kwargs: object):
        from .scene import Scene

        if args and isinstance(args[0], Scene):
            return super().__new__(cls)
        scene = kwargs.get("scene")
        owner = scene if isinstance(scene, Scene) else Scene.current()
        return _adopt(owner.hud.panel(
            position=(float(kwargs.get("x", 0)), float(kwargs.get("y", 0))),
            size=(float(kwargs.get("width", 200)), float(kwargs.get("height", 100))),
            anchor=kwargs.get("anchor", "top_left"),  # type: ignore[arg-type]
            color=kwargs.get("color", (0.08, 0.1, 0.14, 0.85)),  # type: ignore[arg-type]
        ))

    def __init__(self, *args: object, **kwargs: object) -> None:
        if hasattr(self, "_id"):
            return
        super().__init__(args[0], args[1])  # type: ignore[arg-type]


class Sprite(UIElement):
    def __new__(cls, *args: object, **kwargs: object):
        from .scene import Scene

        if args and isinstance(args[0], Scene):
            return super().__new__(cls)
        if not args or not isinstance(args[0], str):
            raise TypeError("Sprite requires a texture path")
        scene = kwargs.get("scene")
        owner = scene if isinstance(scene, Scene) else Scene.current()
        return _adopt(owner.hud.sprite(
            args[0],
            position=(float(kwargs.get("x", 0)), float(kwargs.get("y", 0))),
            size=(float(kwargs.get("width", 64)), float(kwargs.get("height", 64))),
            anchor=kwargs.get("anchor", "top_left"),  # type: ignore[arg-type]
            color=kwargs.get("color", "white"),  # type: ignore[arg-type]
        ))

    def __init__(self, *args: object, **kwargs: object) -> None:
        if hasattr(self, "_id"):
            return
        super().__init__(args[0], args[1])  # type: ignore[arg-type]

    @property
    def texture(self) -> str:
        return str(self._info()[11])


class Text(UIElement):
    def __new__(cls, *args: object, **kwargs: object):
        from .scene import Scene

        if args and isinstance(args[0], Scene):
            return super().__new__(cls)
        if not args or not isinstance(args[0], str):
            raise TypeError("Text requires a text string")
        scene = kwargs.get("scene")
        owner = scene if isinstance(scene, Scene) else Scene.current()
        return _adopt(owner.hud.text(
            args[0],
            position=(float(kwargs.get("x", 20)), float(kwargs.get("y", 20))),
            anchor=kwargs.get("anchor", "top_left"),  # type: ignore[arg-type]
            color=kwargs.get("color", "white"),  # type: ignore[arg-type]
            font_size=float(kwargs.get("font_size", 24)),
        ))

    def __init__(self, *args: object, **kwargs: object) -> None:
        if hasattr(self, "_id"):
            return
        super().__init__(args[0], args[1])  # type: ignore[arg-type]

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

    def __new__(cls, *args: object, **kwargs: object):
        from .scene import Scene

        if args and isinstance(args[0], Scene):
            return super().__new__(cls)
        if not args or not isinstance(args[0], str):
            raise TypeError("Button requires a label string")
        click = kwargs.get("click")
        if click is not None and not callable(click):
            raise TypeError("click must be callable or None")
        scene = kwargs.get("scene")
        owner = scene if isinstance(scene, Scene) else Scene.current()

        def invoke(_button: Button) -> None:
            if click is not None:
                click()  # type: ignore[operator]

        return _adopt(owner.hud.button(
            args[0],
            on_click=None if click is None else invoke,
            position=(float(kwargs.get("x", 0)), float(kwargs.get("y", 0))),
            size=(float(kwargs.get("width", 180)), float(kwargs.get("height", 48))),
            anchor=kwargs.get("anchor", "center"),  # type: ignore[arg-type]
            color=kwargs.get("color", (0.15, 0.32, 0.55, 0.96)),  # type: ignore[arg-type]
        ))

    def __init__(self, *args: object, **kwargs: object) -> None:
        if hasattr(self, "_id"):
            return
        scene, element_id, on_click, normal_color, hover_color, pressed_color = args
        super().__init__(scene, element_id)
        if on_click is not None and not callable(on_click):
            raise TypeError("on_click must be callable or None")
        self.on_click = on_click  # type: ignore[assignment]
        self.normal_color = normal_color  # type: ignore[assignment]
        self.hover_color = hover_color  # type: ignore[assignment]
        self.pressed_color = pressed_color  # type: ignore[assignment]
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

    __slots__ = (
        "direction", "anchor", "position", "spacing", "padding", "margin",
        "alignment", "elements", "_tokens", "_parents",
    )

    def __init__(
        self,
        direction: StackDirection,
        *,
        anchor: Anchor = "center",
        position: tuple[float, float] = (0, 0),
        spacing: float = 8,
        padding: float = 0,
        margin: float = 0,
        alignment: Alignment = "center",
    ) -> None:
        if direction not in ("horizontal", "vertical"):
            raise ValueError("stack direction must be 'horizontal' or 'vertical'")
        if not math.isfinite(spacing) or spacing < 0:
            raise ValueError("stack spacing must be finite and non-negative")
        self.direction = direction
        self.anchor = _anchor(anchor)
        self.position = _pair(position, "position")
        self.spacing = float(spacing)
        self.padding = _space(padding, "padding")
        self.margin = _space(margin, "margin")
        if alignment not in ("start", "center", "end"):
            raise ValueError("alignment must be start, center, or end")
        self.alignment: Alignment = alignment
        self.elements: list[object] = []
        self._tokens: list[Token[object | None]] = []
        self._parents: list[object | None] = []

    @property
    def size(self) -> tuple[float, float]:
        live = self._live()
        sizes = [_item_size(element) for element in live]
        if not sizes:
            content = (0.0, 0.0)
        elif self.direction == "horizontal":
            content = (
                sum(size[0] for size in sizes) + self.spacing * (len(sizes) - 1),
                max(size[1] for size in sizes),
            )
        else:
            content = (
                max(size[0] for size in sizes),
                sum(size[1] for size in sizes) + self.spacing * (len(sizes) - 1),
            )
        inset = 2 * (self.padding + self.margin)
        return content[0] + inset, content[1] + inset

    def _live(self) -> list[object]:
        return [
            element for element in self.elements
            if not bool(getattr(element, "removed", False))
        ]

    def add(self, *elements: object) -> Stack:
        for element in elements:
            _item_size(element)
            if element not in self.elements:
                self.elements.append(element)
        self.relayout()
        return self

    def relayout(self) -> None:
        live = self._live()
        if not live:
            return
        factor_x, factor_y = _anchor_factor(self.anchor)
        sizes = [element.size for element in live]
        width, height = self.size
        left = self.position[0] - width * factor_x + self.margin + self.padding
        top = self.position[1] - height * factor_y + self.margin + self.padding
        content_width = width - 2 * (self.margin + self.padding)
        content_height = height - 2 * (self.margin + self.padding)
        if self.direction == "horizontal":
            cursor = left
            for element, size in zip(live, sizes, strict=True):
                cross = (
                    top if self.alignment == "start"
                    else top + content_height - size[1] if self.alignment == "end"
                    else top + (content_height - size[1]) * 0.5
                )
                _place(element, self.anchor, (
                    cursor + size[0] * factor_x,
                    cross + size[1] * factor_y,
                ))
                cursor += size[0] + self.spacing
        else:
            cursor = top
            for element, size in zip(live, sizes, strict=True):
                cross = (
                    left if self.alignment == "start"
                    else left + content_width - size[0] if self.alignment == "end"
                    else left + (content_width - size[0]) * 0.5
                )
                _place(element, self.anchor, (
                    cross + size[0] * factor_x,
                    cursor + size[1] * factor_y,
                ))
                cursor += size[1] + self.spacing

    def __enter__(self) -> Stack:
        self._parents.append(_current_layout.get())
        self._tokens.append(_current_layout.set(self))
        return self

    def __exit__(self, *_exc: object) -> None:
        if not self._tokens:
            raise RuntimeError("layout context exit without matching enter")
        _current_layout.reset(self._tokens.pop())
        parent = self._parents.pop()
        self.relayout()
        if parent is not None:
            parent.add(self)  # type: ignore[attr-defined]


def Row(
    *elements: UIElement,
    x: float = 0,
    y: float = 0,
    anchor: Anchor = "center",
    spacing: float = 8,
    gap: float | None = None,
    padding: float = 0,
    margin: float = 0,
    alignment: Alignment = "center",
) -> Stack:
    """Lay out retained elements horizontally with practical defaults."""

    return Stack(
        "horizontal", anchor=anchor, position=(float(x), float(y)),
        spacing=spacing if gap is None else gap, padding=padding, margin=margin,
        alignment=alignment,
    ).add(*elements)


def Column(
    *elements: UIElement,
    x: float = 0,
    y: float = 0,
    anchor: Anchor = "center",
    spacing: float = 8,
    gap: float | None = None,
    padding: float = 0,
    margin: float = 0,
    alignment: Alignment = "center",
) -> Stack:
    """Lay out retained elements vertically with practical defaults."""

    return Stack(
        "vertical", anchor=anchor, position=(float(x), float(y)),
        spacing=spacing if gap is None else gap, padding=padding, margin=margin,
        alignment=alignment,
    ).add(*elements)


class Grid:
    """Contextual fixed-column retained layout."""

    def __init__(
        self,
        columns: int = 2,
        *,
        x: float = 0,
        y: float = 0,
        anchor: Anchor = "center",
        gap: float = 8,
        padding: float = 0,
    ) -> None:
        if isinstance(columns, bool) or not isinstance(columns, int) or columns <= 0:
            raise ValueError("columns must be a positive integer")
        self.columns = columns
        self.anchor = _anchor(anchor)
        self.position = (float(x), float(y))
        self.gap = _space(gap, "gap")
        self.padding = _space(padding, "padding")
        self.elements: list[object] = []
        self._tokens: list[Token[object | None]] = []
        self._parents: list[object | None] = []

    def _live(self) -> list[object]:
        return [item for item in self.elements if not bool(getattr(item, "removed", False))]

    @property
    def size(self) -> tuple[float, float]:
        items = self._live()
        if not items:
            return 2 * self.padding, 2 * self.padding
        sizes = [_item_size(item) for item in items]
        widths = [0.0] * self.columns
        rows = math.ceil(len(items) / self.columns)
        heights = [0.0] * rows
        for index, (width, height) in enumerate(sizes):
            widths[index % self.columns] = max(widths[index % self.columns], width)
            heights[index // self.columns] = max(heights[index // self.columns], height)
        return (
            sum(widths) + self.gap * (self.columns - 1) + 2 * self.padding,
            sum(heights) + self.gap * (rows - 1) + 2 * self.padding,
        )

    def add(self, *items: object) -> Grid:
        for item in items:
            _item_size(item)
            if item not in self.elements:
                self.elements.append(item)
        self.relayout()
        return self

    def relayout(self) -> None:
        items = self._live()
        if not items:
            return
        sizes = [_item_size(item) for item in items]
        widths = [0.0] * self.columns
        rows = math.ceil(len(items) / self.columns)
        heights = [0.0] * rows
        for index, (width, height) in enumerate(sizes):
            widths[index % self.columns] = max(widths[index % self.columns], width)
            heights[index // self.columns] = max(heights[index // self.columns], height)
        factor_x, factor_y = _anchor_factor(self.anchor)
        total_width, total_height = self.size
        left = self.position[0] - total_width * factor_x + self.padding
        top = self.position[1] - total_height * factor_y + self.padding
        row_top = top
        for row in range(rows):
            column_left = left
            for column in range(self.columns):
                index = row * self.columns + column
                if index >= len(items):
                    break
                width, height = sizes[index]
                _place(items[index], self.anchor, (
                    column_left + width * factor_x,
                    row_top + height * factor_y,
                ))
                column_left += widths[column] + self.gap
            row_top += heights[row] + self.gap

    def __enter__(self) -> Grid:
        self._parents.append(_current_layout.get())
        self._tokens.append(_current_layout.set(self))
        return self

    def __exit__(self, *_exc: object) -> None:
        _current_layout.reset(self._tokens.pop())
        parent = self._parents.pop()
        self.relayout()
        if parent is not None:
            parent.add(self)  # type: ignore[attr-defined]


class ProgressBar:
    """Two retained panels representing a normalized value."""

    def __init__(
        self,
        value: float = 1.0,
        *,
        x: float = 0,
        y: float = 0,
        width: float = 220,
        height: float = 24,
        anchor: Anchor = "top_left",
        color: ColorValue = "green",
        background: ColorValue = (0.08, 0.1, 0.14, 0.9),
        scene: Scene | None = None,
    ) -> None:
        from .scene import Scene

        owner = scene if isinstance(scene, Scene) else Scene.current()
        self.background = owner.hud.panel(
            position=(float(x), float(y)), size=(float(width), float(height)),
            anchor=anchor, color=background,
        )
        self.fill = owner.hud.panel(
            position=(float(x), float(y)), size=(max(0.001, float(width)), float(height)),
            anchor=anchor, color=color, z_index=self.background.z_index + 1,
        )
        self._value = 1.0
        self.value = value
        _adopt(self)

    @property
    def removed(self) -> bool:
        return self.background.removed

    @property
    def anchor(self) -> Anchor:
        return self.background.anchor

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self.background.anchor = value
        self.fill.anchor = value
        self._sync()

    @property
    def position(self) -> tuple[float, float]:
        return self.background.position

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        self.background.position = value
        self._sync()

    @property
    def size(self) -> tuple[float, float]:
        return self.background.size

    @size.setter
    def size(self, value: tuple[float, float]) -> None:
        self.background.size = value
        self._sync()

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        result = float(value)
        if not math.isfinite(result) or not 0 <= result <= 1:
            raise ValueError("progress value must be between zero and one")
        self._value = result
        self._sync()

    def _sync(self) -> None:
        width, height = self.background.size
        fill_width = max(0.001, width * self._value)
        factor_x, factor_y = _anchor_factor(self.background.anchor)
        self.fill.anchor = self.background.anchor
        self.fill.size = (fill_width, height)
        self.fill.position = (
            self.background.position[0] - width * factor_x + fill_width * factor_x,
            self.background.position[1] - height * factor_y + height * factor_y,
        )

    def remove(self) -> None:
        self.fill.remove()
        self.background.remove()


class HealthBar(ProgressBar):
    """Progress bar bound to an rix.gameplay.Health value."""

    def __init__(self, health: object, **kwargs: object) -> None:
        from .gameplay import Health

        if not isinstance(health, Health):
            raise TypeError("health must be an rix.Health")
        self.health = health
        super().__init__(health.fraction, **kwargs)  # type: ignore[arg-type]
        self._subscription = health.on_change(lambda value: self._set_health(value.fraction))

    def _set_health(self, value: float) -> None:
        self.value = value


class ScoreboardPanel:
    """Native panel/text view bound to a gameplay Scoreboard."""

    def __init__(
        self,
        scoreboard: object,
        *,
        x: float = 20,
        y: float = 20,
        width: float = 260,
        height: float = 180,
        anchor: Anchor = "top_right",
        scene: Scene | None = None,
    ) -> None:
        from .gameplay import Scoreboard
        from .scene import Scene

        if not isinstance(scoreboard, Scoreboard):
            raise TypeError("scoreboard must be an rix.Scoreboard")
        owner = scene if isinstance(scene, Scene) else Scene.current()
        self.scoreboard = scoreboard
        self.panel = owner.hud.panel(
            position=(x, y), size=(width, height), anchor=anchor,
        )
        self.label = owner.hud.text(
            "Scores", position=(x, y), anchor=anchor, font_size=20, z_index=1,
        )
        self._subscription = scoreboard.on_change(lambda _scores: self.sync())
        self.sync()
        _adopt(self)

    @property
    def removed(self) -> bool:
        return self.panel.removed

    @property
    def anchor(self) -> Anchor:
        return self.panel.anchor

    @anchor.setter
    def anchor(self, value: Anchor) -> None:
        self.panel.anchor = value
        self.label.anchor = value

    @property
    def position(self) -> tuple[float, float]:
        return self.panel.position

    @position.setter
    def position(self, value: tuple[float, float]) -> None:
        self.panel.position = value
        factor_x, factor_y = _anchor_factor(self.anchor)
        width, height = self.panel.size
        self.label.position = (
            value[0] - width * factor_x + 12 + self.label.size[0] * factor_x,
            value[1] - height * factor_y + 12 + self.label.size[1] * factor_y,
        )

    @property
    def size(self) -> tuple[float, float]:
        return self.panel.size

    @size.setter
    def size(self, value: tuple[float, float]) -> None:
        self.panel.size = value
        self.position = self.position

    def sync(self) -> None:
        rows = self.scoreboard.ranking
        self.label.text = "Scores" + "".join(
            f"\n{name}: {score}" for name, score in rows
        )
        self.position = self.panel.position

    def relayout(self) -> None:
        self.position = self.panel.position

    def remove(self) -> None:
        self.label.remove()
        self.panel.remove()


Image = Sprite


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
