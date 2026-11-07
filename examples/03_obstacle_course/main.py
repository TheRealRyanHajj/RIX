"""Playable Phase 2 obstacle course using only RIX's public Python API."""

from __future__ import annotations

import argparse
import threading
import time

from rix import (
    Camera,
    Collider,
    Cube,
    Game,
    Light,
    Player,
    Rigidbody,
    Scene,
    Sphere,
)
from rix.input import Binding


class CoursePlayer(Player):
    def __init__(self, *, scene: Scene, game: Game | None, automated: bool) -> None:
        self._game = game
        self._automated = automated
        self._yaw = 0.0
        self._pitch = -8.0
        self._camera_height = 1.55
        self._jump_requested = False
        self.finished = False
        super().__init__(
            position=(0.0, 0.0, 3.0),
            controller="first_person",
            move_speed=4.5,
            move_acceleration=35.0,
            jump_speed=5.5,
            max_slope_degrees=48.0,
            step_height=0.45,
            name="Course player",
            scene=scene,
        )

    def fixed_update(self, dt: float) -> None:
        if self.position.y < -8.0:
            self.controller.teleport((0.0, 0.2, 3.0), heading_degrees=0.0)
            self._yaw = 0.0
        if self._automated:
            self.move((0.0, 0.0, 1.0), heading_degrees=0.0)
            return
        assert self._game is not None
        movement = self._game.input
        self._yaw += movement.value("turn") * 100.0 * dt
        self.move(
            (movement.value("strafe"), 0.0, movement.value("forward")),
            heading_degrees=self._yaw,
            jump=self._jump_requested,
            sprint=movement.down("sprint"),
            crouch=movement.down("crouch"),
        )
        self._jump_requested = False

    def update(self, dt: float) -> None:
        if self._game is not None:
            self._jump_requested = (
                self._jump_requested or self._game.input.pressed("jump")
            )
            pointer_x, pointer_y = self._game.input.pointer.delta
            if self._game.input.pointer_locked:
                self._yaw -= pointer_x * 0.1
                self._pitch = max(-85.0, min(85.0, self._pitch - pointer_y * 0.1))
            if self._game.input.pressed("quit"):
                self._game.stop()
        target_height = 0.95 if self.controller.crouched else 1.55
        self._camera_height += (target_height - self._camera_height) * min(
            1.0, dt * 12.0
        )
        camera = Camera(
            position=(
                self.position.x,
                self.position.y + self._camera_height,
                self.position.z,
            ),
            rotation=(self._pitch, self._yaw, 0.0),
            vertical_fov_degrees=76.0 if self.controller.sprinting else 70.0,
            far_plane=200.0,
        )
        self.scene.camera = camera

    def on_trigger_enter(self, event: object) -> None:
        other = getattr(event, "other", None)
        if other is not None and other.name == "Finish trigger":
            self.finished = True
            print("Obstacle course complete!")


def _bind_controls(game: Game) -> None:
    game.input.bind(
        "forward",
        Binding("key:w", 1.0),
        Binding("key:s", -1.0),
        Binding("key:up", 1.0),
        Binding("key:down", -1.0),
        Binding("gamepad:left_y", -1.0, 0.15),
    )
    game.input.bind(
        "strafe",
        Binding("key:d", 1.0),
        Binding("key:a", -1.0),
        Binding("gamepad:left_x", 1.0, 0.15),
    )
    game.input.bind(
        "turn",
        Binding("key:right", 1.0),
        Binding("key:left", -1.0),
        Binding("gamepad:right_x", 1.0, 0.15),
    )
    game.input.bind("jump", "key:space", "gamepad:a")
    game.input.bind("sprint", "key:left_shift", "key:right_shift")
    game.input.bind("crouch", "key:left_ctrl", "key:right_ctrl")
    # Reserved actions: deliberately unconsumed so games can assign behavior later.
    game.input.bind("tab", "key:tab")
    game.input.bind("q", "key:q")
    game.input.bind("e", "key:e")
    game.input.bind("quit", "key:escape")
    game.input.pointer_lock_requested = True


def build_course(
    *, game: Game | None = None, automated: bool = False
) -> tuple[Scene, CoursePlayer]:
    """Create the playable course; ``automated`` drives its regression lane."""

    if game is not None:
        _bind_controls(game)
    scene = Scene("Physics obstacle course")
    scene.camera = Camera(position=(0.0, 3.0, 8.0), rotation=(-10.0, 0.0, 0.0))
    with scene:
        Light("ambient", color=(0.35, 0.45, 0.65), intensity=0.35)
        Light(
            "directional",
            color=(1.0, 0.9, 0.72),
            intensity=1.2,
            rotation=(-48.0, -25.0, 0.0),
        )
        Cube(
            position=(0.0, -0.5, -8.0),
            size=(16.0, 1.0, 28.0),
            color=(0.18, 0.23, 0.2),
            collider=True,
            name="Course floor",
        )

        # A deterministic three-step climb in the center regression lane.
        for index, top in enumerate((0.2, 0.4, 0.6)):
            Cube(
                position=(0.0, top * 0.5, -2.5 - index),
                size=(3.0, top, 1.0),
                color=(0.78, 0.48 + index * 0.08, 0.18),
                collider=True,
                name=f"Step {index + 1}",
            )
        Cube(
            position=(0.0, 0.3, -7.0),
            size=(3.0, 0.6, 5.0),
            color=(0.28, 0.5, 0.72),
            collider=True,
            name="Raised runway",
        )

        # Optional side challenges: a walkable ramp and narrow balance beams.
        Cube(
            position=(4.0, 0.7, -5.5),
            rotation=(14.0, 0.0, 0.0),
            size=(2.5, 0.25, 6.0),
            color=(0.34, 0.65, 0.35),
            collider=True,
            name="Slope challenge",
        )
        for index in range(3):
            Cube(
                position=(-4.0, 0.45, -4.0 - index * 3.0),
                size=(1.0, 0.3, 2.2),
                color=(0.62, 0.38, 0.2),
                collider=True,
                name=f"Balance beam {index + 1}",
            )

        # Dynamic obstacles demonstrate rigid-body interaction and CCD config.
        for index, x in enumerate((-2.5, 2.5)):
            ball = Sphere(
                position=(x, 3.0 + index, -10.0),
                radius=0.55,
                color=(0.82, 0.2 + index * 0.25, 0.24),
                collider=True,
                name=f"Dynamic ball {index + 1}",
            )
            ball.add_component(Rigidbody, mass=1.5, continuous=True)

        finish = Cube(
            position=(0.0, 1.0, -18.0),
            size=(4.0, 2.0, 0.35),
            color=(0.2, 0.95, 0.45, 0.55),
            collider=False,
            name="Finish trigger",
        )
        finish.add_component(
            Collider,
            half_extents=(2.0, 1.0, 0.175),
            trigger=True,
            layer="sensor",
        )
        player = CoursePlayer(scene=scene, game=game, automated=automated)
    return scene, player


def run(*, seconds: float | None = None) -> None:
    game = Game("RIX — Physics Obstacle Course", (1280, 720), vsync=True)
    scene, player = build_course(game=game)
    game.load_scene(scene)
    if seconds is not None:
        def stop_after_deadline() -> None:
            time.sleep(seconds)
            game.stop()

        threading.Thread(target=stop_after_deadline, daemon=True).start()
    game.run()
    stats = game.renderer_stats
    game.unload_scene(clear=True)
    scene.close()
    print(
        "obstacle_course: PASS "
        f"finished={player.finished} frames={game.frame_count} "
        f"draw_calls={stats.draw_calls} fixed_ticks={game.scheduler_stats.fixed_ticks}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="automatically close after N seconds (default: close interactively)",
    )
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(seconds=arguments.seconds)


if __name__ == "__main__":
    main()
