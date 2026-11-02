"""Strict-mypy consumer coverage for representative documented public APIs."""

from pathlib import Path
from typing import assert_type

from easy3d import (
    AssetDiagnostic,
    DebugOverlay,
    Entity,
    Game,
    GltfInfo,
    JointPose,
    Model,
    RendererStats,
    Scene,
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
assert_type(scene.entities, tuple[Entity, ...])
assert_type(model.position, Vec3)
assert_type(overlay, DebugOverlay)
assert_type(report, AssetDiagnostic)
assert_type(imported, GltfInfo)
if imported.skeleton is not None:
    assert_type(
        imported.animations[0].sample(imported.skeleton, 0.5),
        tuple[JointPose, ...],
    )
