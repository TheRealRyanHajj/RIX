"""Strict-mypy consumer coverage for representative documented public APIs."""

from pathlib import Path
from typing import Any, assert_type

from rix import (
    AssetDiagnostic,
    AudioSource,
    Cube,
    CullMode,
    DebugOverlay,
    Entity,
    Game,
    GltfInfo,
    HitscanWeapon,
    JointPose,
    LightKind,
    MeshRenderer,
    Model,
    PhysicsHit,
    Player,
    RendererStats,
    Scene,
    Timer,
    Tween,
    Vec3,
    diagnose_asset,
    load_gltf,
)


game = Game("typed", (800, 450), graphics_preset="high")
scene = Scene("typed")
with scene:
    model = Model(Path("asset.glb"), position=(0, 0, 0))

overlay = DebugOverlay(game, scene=scene)
report = diagnose_asset(Path("asset.glb"))
imported = load_gltf(Path("asset.glb"))
assert_type(game.renderer_stats, RendererStats)
assert_type(game.renderer_stats.gpu_frame_ms, float)
assert_type(game.running, bool)
assert_type(game.tick(60), float)
assert_type(scene.entities, tuple[Entity, ...])
assert_type(model.position, Vec3)
cube = Cube(
    velocity=(1, 0, 0),
    acceleration=(0, -9.81, 0),
    angular_velocity=(0, 90, 0),
    angular_acceleration=(0, -10, 0),
    texture=Path("brick.png"),
    pixels_per_unit=32,
    texture_filter="nearest",
    texture_mode="atlas",
    normal_map=False,
    metallic=0.5,
    roughness=0.8,
    emission=0.0,
    double_sided=True,
)
renderer = cube.get_component(MeshRenderer)
assert_type(renderer, MeshRenderer | None)
mode: CullMode = "front"
light_kind: LightKind = "point"
cube.cull_mode = mode
assert_type(light_kind, LightKind)
assert_type(cube.cull_mode, CullMode)
assert_type(cube.double_sided, bool)
assert_type(cube.velocity, Vec3)
assert_type(cube.acceleration, Vec3)
assert_type(cube.angular_velocity, Vec3)
assert_type(cube.angular_acceleration, Vec3)
assert_type(cube.speed, float)
assert_type(cube.movement_direction, Vec3)
assert_type(cube.forward, Vec3)
assert_type(cube.local_to_world_direction((0, 0, -1)), Vec3)
assert_type(cube.launch((0, 0, -1), 20, face=True), Entity)
assert_type(cube.teleport((0, 2, 0), reset_motion=True), Entity)
if renderer is not None:
    renderer.double_sided = True
    assert_type(renderer.cull_mode, CullMode)
assert_type(overlay, DebugOverlay)
assert_type(report, AssetDiagnostic)
assert_type(imported, GltfInfo)
assert_type(
    game.raycast((0, 0, 0), (0, 0, -1), distance=10), PhysicsHit | None
)
assert_type(game.play_sound(Path("sound.wav")), AudioSource)
timer = Timer(1)
game.manage_timer(timer)
player = Player(y=2, move_speed=6, move_acceleration=35)
assert_type(player.raycast(5), PhysicsHit | None)
assert_type(player.add_weapon(), HitscanWeapon)
assert_type(player.view_forward, Vec3)
assert_type(player.view_right, Vec3)
assert_type(player.view_up, Vec3)
assert_type(model.animate("y", to=5, duration=1), Tween[Any])
if imported.skeleton is not None:
    assert_type(
        imported.animations[0].sample(imported.skeleton, 0.5),
        tuple[JointPose, ...],
    )
