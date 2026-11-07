"""Pygame Community Edition integration without taking over its event loop."""

from __future__ import annotations

import math
import sys
from typing import TYPE_CHECKING, Any, Literal

from .game import Game, GraphicsPreset, Lighting, RendererStats
from .textures import SurfaceTexture, coerce_surface_texture

if TYPE_CHECKING:
    import pygame
    from .camera import Camera
    from .net.session import Session


def _pygame() -> Any:
    try:
        import pygame
    except ImportError as error:
        raise ImportError(
            "RIX Pygame integration requires pygame-ce; install rix[pygame]"
        ) from error
    return pygame


def _canonical_name(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


class World:
    """A RIX 3D world presented into a Pygame-owned Windows display.

    Pygame owns the window, application loop, timing, and event queue. RIX owns
    the bgfx swap chain and final presentation. Consequently applications must
    not call ``pygame.display.flip()`` or ``pygame.display.update()`` in this
    direct GPU mode. Draw Pygame UI to a separate Surface and pass it to the
    composition API rather than drawing to the display Surface.
    """

    __slots__ = (
        "_game",
        "_pygame",
        "_screen",
        "_native_window",
        "_closed",
        "_running",
        "_paused",
        "_pointer_grabbed",
        "_overlay_texture",
        "_overlay_id",
        "_mode",
        "_sessions",
    )

    def __init__(
        self,
        screen: pygame.Surface,
        *,
        fixed_hz: float = 60.0,
        max_frame_seconds: float = 0.25,
        max_catch_up_steps: int = 5,
        fail_fast: bool = True,
        graphics_preset: GraphicsPreset = "medium",
        auto_setup: bool = True,
        mode: Literal["gpu", "surface"] = "gpu",
        vsync: bool = True,
    ) -> None:
        pygame_module = _pygame()
        if sys.platform != "win32":
            raise RuntimeError(
                "Pygame-owned GPU presentation is currently supported on Windows only"
            )
        if not isinstance(screen, pygame_module.Surface):
            raise TypeError("screen must be a pygame.Surface")
        if pygame_module.display.get_surface() is not screen:
            raise ValueError("screen must be the active pygame display Surface")
        width, height = screen.get_size()
        if width <= 0 or height <= 0:
            raise ValueError("the Pygame display must have a positive size")
        native_window = self._read_native_window(pygame_module)
        if mode not in ("gpu", "surface"):
            raise ValueError("mode must be 'gpu' or 'surface'")
        if not isinstance(vsync, bool):
            raise TypeError("vsync must be a bool")

        self._pygame = pygame_module
        self._screen = screen
        self._native_window = native_window
        self._closed = False
        self._running = True
        self._paused = False
        self._pointer_grabbed = False
        self._overlay_texture: SurfaceTexture | None = None
        self._overlay_id: int | None = None
        self._mode = mode
        self._sessions: dict[Session, bool] = {}
        self._game = Game(
            "RIX for Pygame",
            (width, height),
            vsync,
            0,
            fixed_hz=fixed_hz,
            max_frame_seconds=max_frame_seconds,
            max_catch_up_steps=max_catch_up_steps,
            fail_fast=fail_fast,
            graphics_preset=graphics_preset,
            auto_setup=auto_setup,
        )
        try:
            self._game._begin_external_loop()
            self._game._engine.begin_external_window(
                native_window, width, height
            )
            self._game.input._native._begin_frame()
        except Exception:
            self._game._finish_external_loop()
            self._game.close()
            self._closed = True
            self._running = False
            raise

    @staticmethod
    def _read_native_window(pygame_module: Any) -> int:
        info = pygame_module.display.get_wm_info()
        value = info.get("window")
        if not isinstance(value, int) or value == 0:
            raise RuntimeError(
                "Pygame did not expose a valid Win32 window handle; "
                "create the display with pygame.display.set_mode() first"
            )
        return value

    @property
    def game(self) -> Game:
        """Underlying standalone-compatible Game facade."""

        return self._game

    @property
    def scene(self):
        return self._game.scene

    @property
    def camera(self):
        return self._game.camera

    @property
    def input(self):
        return self._game.input

    @property
    def lighting(self) -> Lighting:
        return self._game.lighting

    @property
    def skybox(self):
        return self._game.skybox

    @skybox.setter
    def skybox(self, value: object) -> None:
        self._game.skybox = value

    @property
    def renderer_stats(self) -> RendererStats:
        return self._game.renderer_stats

    @property
    def overlay(self) -> SurfaceTexture | None:
        return self._overlay_texture

    @property
    def mode(self) -> Literal["gpu", "surface"]:
        return self._mode

    @property
    def running(self) -> bool:
        return self._running and not self._closed

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._require_open()
        self._paused = True

    def resume(self) -> None:
        self._require_open()
        self._paused = False

    def stop(self) -> None:
        self._running = False

    def attach_session(
        self, session: Session, *, close_with_world: bool = True
    ) -> Session:
        """Pump one open-or-future Session from :meth:`update`.

        An attached session must not also be polled manually. Networking keeps
        pumping while the world's simulation is paused. By default the session
        is closed before the Pygame-backed renderer during world shutdown.
        """

        from .net.session import Session

        self._require_open()
        if not isinstance(session, Session):
            raise TypeError("session must be a rix.net.Session")
        if not isinstance(close_with_world, bool):
            raise TypeError("close_with_world must be a bool")
        if session in self._sessions:
            raise ValueError("session is already attached to this World")
        self._sessions[session] = close_with_world
        return session

    def detach_session(self, session: Session, *, close: bool = False) -> bool:
        """Stop automatic polling and optionally close the detached session."""

        from .net.session import Session

        self._require_open()
        if not isinstance(session, Session):
            raise TypeError("session must be a rix.net.Session")
        if not isinstance(close, bool):
            raise TypeError("close must be a bool")
        if session not in self._sessions:
            return False
        del self._sessions[session]
        if close:
            session.close("detached from World")
        return True

    @property
    def sessions(self) -> tuple[Session, ...]:
        """Sessions automatically polled by this world, in attachment order."""

        return tuple(self._sessions)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("World is closed")

    def _sync_display(self) -> None:
        current_screen = self._pygame.display.get_surface()
        if current_screen is None:
            raise RuntimeError("the Pygame display was closed before the RIX World")
        width, height = current_screen.get_size()
        native_window = self._read_native_window(self._pygame)
        if native_window != self._native_window:
            self._game._engine.end_external_window()
            self._game._engine.begin_external_window(native_window, width, height)
            self._native_window = native_window
            self._resize_overlay(width, height)
        elif tuple(self._game._engine.viewport_size) != (width, height):
            self._game._engine.resize_external_window(width, height)
            self._resize_overlay(width, height)
        self._screen = current_screen

    def _resize_overlay(self, width: int, height: int) -> None:
        if self._overlay_id is None or self.scene is None:
            return
        self.scene._native.update_ui_element(
            self._overlay_id,
            "top_left",
            (0.0, 0.0),
            (float(width), float(height)),
            (1.0, 1.0, 1.0, 1.0),
            "",
            (1.0, 1.0, 1.0, 1.0),
            4.0,
            2_000_000_000,
            True,
            True,
        )

    def set_overlay(self, surface: object | SurfaceTexture | None) -> None:
        """Set a full-window Pygame UI layer composited after RIX 3D.

        Pass a transparent ``pygame.Surface`` or a reusable
        :class:`SurfaceTexture`. Call ``world.overlay.update(surface)`` after
        later Pygame drawing changes; updates are never implicit.
        """

        self._require_open()
        if self._mode != "gpu":
            raise RuntimeError(
                "surface mode uses ordinary Pygame blits; draw UI to the display "
                "after blitting the returned 3D Surface"
            )
        scene = self.scene
        if scene is None:
            raise RuntimeError("World has no active scene")
        if surface is None:
            if self._overlay_id is not None:
                scene._native.remove_ui_element(self._overlay_id)
            self._overlay_id = None
            self._overlay_texture = None
            return
        texture = coerce_surface_texture(surface)
        if texture is None:
            raise TypeError("overlay must be a pygame.Surface or rix.SurfaceTexture")
        width, height = self._screen.get_size()
        if self._overlay_id is None:
            self._overlay_id = scene._native.add_ui_element(
                "panel",
                "top_left",
                (0.0, 0.0),
                (float(width), float(height)),
                (1.0, 1.0, 1.0, 1.0),
                "",
                (1.0, 1.0, 1.0, 1.0),
                4.0,
                2_000_000_000,
                True,
                True,
                None,
            )
        scene._native.set_ui_image(self._overlay_id, texture._native)
        self._overlay_texture = texture

    def _sync_pointer_capture(self) -> None:
        requested = self.input.pointer_lock_requested and self.input.focused
        if requested == self._pointer_grabbed:
            return
        self._pygame.event.set_grab(requested)
        self._pygame.mouse.set_visible(not requested)
        self.input._native._set_pointer_lock_active(requested)
        self._pointer_grabbed = requested

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Forward one already-polled Pygame event into RIX.

        Returns ``True`` when RIX recognized the event. The event remains fully
        available to the application; RIX never drains Pygame's queue.
        """

        self._require_open()
        pygame_module = self._pygame
        event_type = getattr(event, "type", None)
        if not isinstance(event_type, int):
            raise TypeError("event must be a pygame.event.Event")
        native = self.input._native

        if event_type == pygame_module.QUIT:
            self._running = False
            return True
        if event_type in (pygame_module.KEYDOWN, pygame_module.KEYUP):
            if bool(getattr(event, "repeat", False)):
                return True
            name = _canonical_name(pygame_module.key.name(event.key))
            native._set_control(
                f"key:{name}", 1.0 if event_type == pygame_module.KEYDOWN else 0.0
            )
            return True
        if event_type == pygame_module.MOUSEMOTION:
            x, y = event.pos
            dx, dy = event.rel
            native._add_pointer_motion(float(x), float(y), float(dx), float(dy))
            return True
        if event_type in (pygame_module.MOUSEBUTTONDOWN, pygame_module.MOUSEBUTTONUP):
            names = {1: "left", 2: "middle", 3: "right", 4: "x1", 5: "x2"}
            name = names.get(int(event.button), f"button_{int(event.button)}")
            native._set_control(
                f"mouse:{name}",
                1.0 if event_type == pygame_module.MOUSEBUTTONDOWN else 0.0,
            )
            return True
        if event_type == pygame_module.MOUSEWHEEL:
            native._add_wheel(float(event.x), float(event.y))
            return True

        focus_gained = {
            getattr(pygame_module, name, -1)
            for name in ("WINDOWFOCUSGAINED", "ACTIVEEVENT")
        }
        focus_lost = {getattr(pygame_module, "WINDOWFOCUSLOST", -1)}
        if event_type in focus_gained:
            if event_type == getattr(pygame_module, "ACTIVEEVENT", -1):
                focused = bool(getattr(event, "gain", 0))
                native._set_focused(focused)
            else:
                native._set_focused(True)
            return True
        if event_type in focus_lost:
            native._set_focused(False)
            return True

        resize_types = {
            getattr(pygame_module, name, -1)
            for name in ("VIDEORESIZE", "WINDOWRESIZED", "WINDOWSIZECHANGED")
        }
        if event_type in resize_types:
            self._sync_display()
            return True

        controller_added = {
            getattr(pygame_module, name, -1)
            for name in ("JOYDEVICEADDED", "CONTROLLERDEVICEADDED")
        }
        controller_removed = {
            getattr(pygame_module, name, -1)
            for name in ("JOYDEVICEREMOVED", "CONTROLLERDEVICEREMOVED")
        }
        if event_type in controller_added:
            native._set_gamepad_connected(True, "Pygame controller")
            return True
        if event_type in controller_removed:
            native._set_gamepad_connected(False, "")
            return True

        button_down = {
            getattr(pygame_module, name, -1)
            for name in ("JOYBUTTONDOWN", "CONTROLLERBUTTONDOWN")
        }
        button_up = {
            getattr(pygame_module, name, -1)
            for name in ("JOYBUTTONUP", "CONTROLLERBUTTONUP")
        }
        if event_type in button_down | button_up:
            button = int(getattr(event, "button", 0))
            button_names = {
                0: "a",
                1: "b",
                2: "x",
                3: "y",
                4: "back",
                5: "guide",
                6: "start",
                7: "left_stick",
                8: "right_stick",
                9: "left_shoulder",
                10: "right_shoulder",
                11: "dpad_up",
                12: "dpad_down",
                13: "dpad_left",
                14: "dpad_right",
            }
            name = button_names.get(button, f"button_{button}")
            native._set_control(
                f"gamepad:{name}", 1.0 if event_type in button_down else 0.0
            )
            return True
        axis_types = {
            getattr(pygame_module, name, -1)
            for name in ("JOYAXISMOTION", "CONTROLLERAXISMOTION")
        }
        if event_type in axis_types:
            axis = int(getattr(event, "axis", 0))
            value = float(getattr(event, "value", 0.0))
            axis_names = {
                0: "left_x",
                1: "left_y",
                2: "right_x",
                3: "right_y",
                4: "left_trigger",
                5: "right_trigger",
            }
            name = axis_names.get(axis, f"axis_{axis}")
            native._set_control(f"gamepad:{name}", value)
            return True
        return False

    def update(self, dt: float) -> None:
        """Advance scripts and fixed-step physics using seconds supplied by Pygame."""

        self._require_open()
        if isinstance(dt, bool) or not isinstance(dt, (int, float)):
            raise TypeError("dt must be a number of seconds")
        elapsed = float(dt)
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("dt must be finite and non-negative")
        for session in tuple(self._sessions):
            session.update(elapsed)
        self._sync_pointer_capture()
        self.input._native._end_frame()
        if not self._paused:
            self._game._advance_external_frame(elapsed)
        self.input._native._begin_frame()

    def render(self):
        """Render one frame and return a Surface only in compatibility mode.

        In ``mode='gpu'`` RIX presents and the return value is ``None``. In
        ``mode='surface'`` RIX never presents; the returned Surface is for the
        application to blit before its ordinary ``pygame.display.flip()``.
        """

        self._require_open()
        self._sync_display()
        if self._mode == "gpu":
            self._game._engine.render_external_window()
            return None
        self._game._engine.render_external_offscreen()
        return self.to_surface()

    def to_surface(self):
        """Synchronously read the last 3D frame into an owned Pygame Surface.

        GPU readback stalls and is intended for compatibility viewports, not
        full-window high-frame-rate rendering. Use direct GPU mode when possible.
        """

        self._require_open()
        width, height = self._game._engine.viewport_size
        rgba8 = self._game._engine.readback_external_window_rgba8()
        expected = width * height * 4
        if len(rgba8) != expected:
            raise RuntimeError("native Surface readback returned an invalid byte count")
        return self._pygame.image.frombytes(rgba8, (width, height), "RGBA").copy()

    @staticmethod
    def _viewport_arguments(camera: Camera, size: tuple[int, int]) -> tuple[object, ...]:
        quaternion = camera.quaternion
        return (
            camera.position.x,
            camera.position.y,
            camera.position.z,
            quaternion.w,
            quaternion.x,
            quaternion.y,
            quaternion.z,
            camera.vertical_fov_degrees,
            camera.near_plane,
            camera.far_plane,
            camera.projection == "orthographic",
            camera.orthographic_height,
            size[0],
            size[1],
        )

    def _viewport_surface(self, rgba8: bytes, size: tuple[int, int]):
        expected = size[0] * size[1] * 4
        if len(rgba8) != expected:
            raise RuntimeError("native Viewport readback returned an invalid byte count")
        return self._pygame.image.frombytes(rgba8, size, "RGBA").copy()

    def _render_viewport(self, camera: Camera, size: tuple[int, int]):
        self._require_open()
        self._sync_display()
        rgba8 = self._game._engine.render_external_viewport_rgba8(
            *self._viewport_arguments(camera, size)
        )
        return self._viewport_surface(rgba8, size)

    def _request_viewport(self, camera: Camera, size: tuple[int, int]) -> int:
        self._require_open()
        self._sync_display()
        return int(
            self._game._engine.request_external_viewport_rgba8(
                *self._viewport_arguments(camera, size)
            )
        )

    def _poll_viewport(self, request_id: int, size: tuple[int, int]):
        self._require_open()
        rgba8 = self._game._engine.poll_external_viewport_rgba8(request_id)
        if rgba8 is None:
            return None
        return self._viewport_surface(rgba8, size)

    def _wait_viewport(self, request_id: int, size: tuple[int, int]):
        self._require_open()
        rgba8 = self._game._engine.wait_external_viewport_rgba8(request_id)
        return self._viewport_surface(rgba8, size)

    def _cancel_viewport(self, request_id: int) -> None:
        if not self._closed:
            self._game._engine.cancel_external_viewport_rgba8(request_id)

    def close(self) -> None:
        """Release bgfx before the application destroys Pygame's window."""

        if self._closed:
            return
        if self._pointer_grabbed:
            self._pygame.event.set_grab(False)
            self._pygame.mouse.set_visible(True)
            self._pointer_grabbed = False
        session_error: BaseException | None = None
        for session, close_with_world in tuple(self._sessions.items()):
            if not close_with_world:
                continue
            try:
                session.close("owning World closed")
            except BaseException as error:
                if session_error is None:
                    session_error = error
        self._sessions.clear()
        self._game._finish_external_loop()
        self._game.close()
        self._closed = True
        self._running = False
        if session_error is not None:
            raise session_error

    def __enter__(self) -> World:
        self._require_open()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

