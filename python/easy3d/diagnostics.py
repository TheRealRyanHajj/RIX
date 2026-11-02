"""Structured asset checks and a native-rendered runtime debug overlay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Literal, TypeAlias

from ._easy3d import AssetError
from .assets import GltfInfo, ModelInfo, load_gltf, load_image, load_obj
from .entity import Entity
from .game import Game
from .scene import Scene
from .ui import Anchor, Panel, Text


AssetKind: TypeAlias = Literal["image", "obj", "gltf", "unknown"]


@dataclass(frozen=True, slots=True)
class AssetDiagnostic:
    """One non-throwing asset validation result with user-facing context."""

    path: Path
    kind: AssetKind
    ok: bool
    summary: str
    warnings: tuple[str, ...] = ()
    width: int | None = None
    height: int | None = None
    triangle_count: int | None = None
    part_count: int | None = None
    material_count: int | None = None
    joint_count: int | None = None
    clip_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None


def _asset_kind(path: Path) -> AssetKind:
    extension = path.suffix.lower()
    if extension in (".png", ".jpg", ".jpeg"):
        return "image"
    if extension == ".obj":
        return "obj"
    if extension in (".gltf", ".glb"):
        return "gltf"
    return "unknown"


def diagnose_asset(path: str | PathLike[str]) -> AssetDiagnostic:
    """Validate a supported asset and return diagnostics instead of raising.

    Programming errors such as a non-path argument still raise ``TypeError``.
    File/import failures are captured with the exact native exception type and
    message so tools can present them without parsing console output.
    """

    if not isinstance(path, (str, PathLike)):
        raise TypeError("path must be a string or path-like object")
    candidate = Path(path)
    kind = _asset_kind(candidate)
    display_path = candidate.resolve(strict=False)
    if kind == "unknown":
        message = (
            f"unsupported asset format '{candidate.suffix}' for {candidate}; "
            "supported: .png, .jpg, .jpeg, .obj, .gltf, .glb"
        )
        return AssetDiagnostic(
            display_path,
            kind,
            False,
            "unsupported asset format",
            error_type="AssetError",
            error_message=message,
        )
    try:
        if kind == "image":
            image = load_image(candidate)
            return AssetDiagnostic(
                image.path,
                kind,
                True,
                f"{image.width}x{image.height} RGBA8 image",
                width=image.width,
                height=image.height,
            )
        model: ModelInfo | GltfInfo
        if kind == "obj":
            model = load_obj(candidate)
            joints = clips = None
        else:
            gltf = load_gltf(candidate)
            model = gltf
            joints = len(gltf.skeleton.joints) if gltf.skeleton is not None else 0
            clips = len(gltf.animations)
        return AssetDiagnostic(
            model.path,
            kind,
            True,
            f"{model.triangle_count} triangles in {len(model.parts)} parts",
            warnings=model.warnings,
            triangle_count=model.triangle_count,
            part_count=len(model.parts),
            material_count=len(model.materials),
            joint_count=joints,
            clip_count=clips,
        )
    except AssetError as error:
        return AssetDiagnostic(
            display_path,
            kind,
            False,
            "asset validation failed",
            error_type=type(error).__name__,
            error_message=str(error),
        )


class DebugOverlay(Entity):
    """Small native HUD panel showing live renderer and scheduler diagnostics."""

    def __init__(
        self,
        game: Game,
        *,
        scene: Scene | None = None,
        anchor: Anchor = "top_left",
        position: tuple[float, float] = (12, 12),
        refresh_interval: float = 0.25,
        z_index: int = 10_000,
    ) -> None:
        if not isinstance(game, Game):
            raise TypeError("game must be an easy3d.Game")
        if isinstance(refresh_interval, bool) or not isinstance(
            refresh_interval, (int, float)
        ):
            raise TypeError("refresh_interval must be a number")
        if not math.isfinite(refresh_interval) or refresh_interval <= 0:
            raise ValueError("refresh_interval must be finite and positive")
        super().__init__("Easy3D debug overlay", scene=scene)
        self._game = game
        self._refresh_interval = float(refresh_interval)
        self._elapsed = self._refresh_interval
        self._smoothed_fps = 0.0
        text_position = (
            position[0] + (12 if anchor.endswith("left") else -12 if anchor.endswith("right") else 0),
            position[1] + (10 if anchor.startswith("top") else -10 if anchor.startswith("bottom") else 0),
        )
        self._panel: Panel = self.scene.hud.panel(
            position=position,
            size=(430, 188),
            anchor=anchor,
            color=(0.025, 0.035, 0.055, 0.88),
            z_index=z_index,
        )
        self._text: Text = self.scene.hud.text(
            "Easy3D diagnostics",
            position=text_position,
            anchor=anchor,
            color=(0.86, 0.94, 1.0, 1.0),
            font_size=15,
            z_index=z_index + 1,
        )

    @property
    def panel(self) -> Panel:
        return self._panel

    @property
    def text(self) -> Text:
        return self._text

    def show(self) -> None:
        self._panel.visible = True
        self._text.visible = True

    def hide(self) -> None:
        self._panel.visible = False
        self._text.visible = False

    def update(self, delta_seconds: float) -> None:
        if delta_seconds > 0:
            instant = 1.0 / delta_seconds
            self._smoothed_fps = (
                instant
                if self._smoothed_fps == 0
                else self._smoothed_fps * 0.9 + instant * 0.1
            )
        self._elapsed += max(0.0, delta_seconds)
        if self._elapsed < self._refresh_interval:
            return
        self._elapsed = 0.0
        render = self._game.renderer_stats
        scheduler = self._game.scheduler_stats
        features = ", ".join(
            name
            for name, active in (
                ("enhanced", render.enhanced_lighting),
                ("shadows", render.shadows),
                ("post", render.postprocessing),
                ("fxaa", render.fxaa),
            )
            if active
        ) or "baseline"
        maximum_callback_ms = max(
            (callback.max_seconds * 1000 for callback in scheduler.callbacks.values()),
            default=0.0,
        )
        self._text.text = (
            "Easy3D diagnostics\n"
            f"FPS {self._smoothed_fps:6.1f} | frame {self._game.last_frame_seconds * 1000:6.2f} ms\n"
            f"entities {self.scene.entity_count} | fixed ticks {scheduler.fixed_ticks}\n"
            f"draws {render.draw_calls} | instanced {render.instanced_draw_calls}\n"
            f"visible {render.visible_instances} | culled {render.culled_instances}\n"
            f"UI {render.ui_elements}/{render.ui_draw_calls} | callback max {maximum_callback_ms:.2f} ms\n"
            f"overruns {scheduler.overrun_count} | dropped {scheduler.dropped_seconds:.4f} s\n"
            f"features {features}"
        )
