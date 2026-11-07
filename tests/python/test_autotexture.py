from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import rix as e3


def test_game_texture_defaults_and_overrides() -> None:
    game = e3.Game(auto_setup=False)
    assert game.pixels_per_unit == 16
    assert game.texture_filter == "nearest"
    assert game.texture_mode == "auto"
    assert game.texture_hot_reload is True
    game.close()

    configured = e3.Game(
        auto_setup=False,
        pixels_per_unit=32,
        texture_filter="linear",
        texture_mode="tile",
        texture_hot_reload=False,
    )
    assert configured.pixels_per_unit == 32
    assert configured.texture_filter == "linear"
    assert configured.texture_mode == "tile"
    assert configured.texture_hot_reload is False
    configured.close()


def test_missing_tile_and_neutral_normal_are_generated(tmp_path: Path) -> None:
    scene = e3.Scene()
    path = tmp_path / "nested" / "brick.png"
    cube = e3.Cube(texture=path, scene=scene)
    normal = tmp_path / "nested" / "brick_normal.png"

    assert path.is_file()
    assert normal.is_file()
    assert e3.load_image(path).width == 16
    assert e3.load_image(path).height == 16
    normal_info = e3.load_image(normal, color_space="linear")
    assert (normal_info.width, normal_info.height) == (16, 16)

    renderer = cube.get_component(e3.MeshRenderer)
    assert renderer is not None
    assert renderer.texture == path.resolve()
    assert renderer.normal_map == normal.resolve()
    assert renderer.pixels_per_unit == 16
    assert renderer.texture_filter == "nearest"
    assert renderer.texture_mode == "tile"
    assert renderer.normal_strength == 1
    scene.close()


def test_global_and_per_object_density_drive_generated_resolution(tmp_path: Path) -> None:
    game = e3.Game(auto_setup=True, pixels_per_unit=32)
    global_texture = tmp_path / "global.png"
    overridden_texture = tmp_path / "overridden.png"
    e3.Cube(texture=global_texture)
    overridden = e3.Cube(texture=overridden_texture, pixels_per_unit=48)

    assert e3.load_image(global_texture).width == 32
    assert e3.load_image(overridden_texture).width == 48
    renderer = overridden.get_component(e3.MeshRenderer)
    assert renderer is not None
    assert renderer.pixels_per_unit == 48
    game.close()


def test_sphere_template_is_two_to_one_and_uses_spherical_mode(tmp_path: Path) -> None:
    scene = e3.Scene()
    path = tmp_path / "sphere.png"
    sphere = e3.Sphere(texture=path, scene=scene)
    image = e3.load_image(path)
    metadata = json.loads(path.with_suffix(".texture.json").read_text())
    renderer = sphere.get_component(e3.MeshRenderer)

    assert (image.width, image.height) == (32, 16)
    assert metadata["layout"] == "rix-spherical-v1"
    assert renderer is not None
    assert renderer.texture_mode == "sphere"
    scene.close()


def test_rectangular_cube_atlas_dimensions_and_metadata(tmp_path: Path) -> None:
    scene = e3.Scene()
    path = tmp_path / "crate.png"
    e3.Cube(size=(2, 3, 1), texture=path, texture_mode="atlas", scene=scene)
    info = e3.load_image(path)
    assert (info.width, info.height) == (96, 80)

    metadata = json.loads(path.with_suffix(".texture.json").read_text())
    assert metadata["layout"] == "rix-cube-cross-v1"
    assert set(metadata["faces"]) == {
        "top",
        "bottom",
        "front",
        "back",
        "left",
        "right",
    }
    scene.close()


def test_atlas_layout_is_stable_under_parent_and_runtime_scaling(
    tmp_path: Path,
) -> None:
    scene = e3.Scene()
    parent = e3.Entity(scene=scene)
    parent.scale = (2, 0.5, 3)
    path = tmp_path / "scaled-crate.png"
    cube = e3.Cube(
        size=(2, 3, 1),
        parent=parent,
        texture=path,
        texture_mode="atlas",
        collider=False,
    )
    renderer = cube.get_component(e3.MeshRenderer)
    assert renderer is not None

    # The generated cross uses the initial world dimensions (4, 1.5, 3), so
    # each atlas face receives pixel area proportional to its visible size.
    assert (e3.load_image(path).width, e3.load_image(path).height) == (224, 120)
    native_info = scene._native.render_component_info(cube._handle)
    assert tuple(native_info[19]) == pytest.approx((4, 1.5, 3))

    # Later nonuniform local/parent scaling must not shift the fixed PNG face
    # regions, and ordinary runtime material changes must not create a false
    # template conflict. A density change is layout-compatible as well.
    cube.scale = (5, 2, 4)
    parent.scale = (3, 4, 0.5)
    renderer.normal_strength = 0.4
    renderer.pixels_per_unit = 32
    native_info = scene._native.render_component_info(cube._handle)
    assert tuple(native_info[19]) == pytest.approx((4, 1.5, 3))
    assert renderer.normal_strength == pytest.approx(0.4)
    assert renderer.pixels_per_unit == pytest.approx(32)
    assert (e3.load_image(path).width, e3.load_image(path).height) == (224, 120)
    scene.close()


def test_atlas_conflict_uses_face_proportions_not_absolute_resolution(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared-atlas.png"
    first = e3.Scene()
    e3.Cube(
        size=(2, 3, 1),
        texture=path,
        pixels_per_unit=16,
        texture_mode="atlas",
        scene=first,
    )
    first.close()

    compatible = e3.Scene()
    e3.Cube(
        size=(4, 6, 2),
        texture=path,
        pixels_per_unit=32,
        texture_mode="atlas",
        scene=compatible,
    )
    compatible.close()

    conflicting = e3.Scene()
    with pytest.raises(e3.AssetError, match="face layout"):
        e3.Cube(
            size=(2, 1, 1),
            texture=path,
            texture_mode="atlas",
            scene=conflicting,
        )
    conflicting.close()


def test_deleted_generated_atlas_validates_and_refreshes_retained_sidecars(
    tmp_path: Path,
) -> None:
    path = tmp_path / "regenerated-atlas.png"
    normal = tmp_path / "regenerated-atlas_normal.png"
    first = e3.Scene()
    e3.Cube(
        size=(2, 3, 1),
        texture=path,
        pixels_per_unit=16,
        texture_mode="atlas",
        scene=first,
    )
    first.close()
    path.unlink()
    normal.unlink()

    incompatible = e3.Scene()
    with pytest.raises(e3.AssetError, match="face layout"):
        e3.Cube(
            size=(2, 1, 1),
            texture=path,
            texture_mode="atlas",
            scene=incompatible,
        )
    assert not path.exists()
    assert not normal.exists()
    incompatible.close()

    compatible = e3.Scene()
    e3.Cube(
        size=(4, 6, 2),
        texture=path,
        pixels_per_unit=32,
        texture_mode="atlas",
        scene=compatible,
    )
    assert (e3.load_image(path).width, e3.load_image(path).height) == (384, 320)
    metadata = json.loads(path.with_suffix(".texture.json").read_text())
    normal_metadata = json.loads(normal.with_suffix(".texture.json").read_text())
    assert (metadata["width"], metadata["height"]) == (384, 320)
    assert (normal_metadata["width"], normal_metadata["height"]) == (384, 320)
    compatible.close()


def test_existing_texture_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "owned.png"
    original = b"not actually a PNG"
    path.write_bytes(original)
    scene = e3.Scene()
    with pytest.raises(e3.AssetError):
        e3.Cube(texture=path, scene=scene)
    assert path.read_bytes() == original
    assert not path.with_name("owned_normal.png").exists()
    scene.close()


def test_missing_unsupported_extension_and_directory_target_fail_cleanly(
    tmp_path: Path,
) -> None:
    scene = e3.Scene()
    with pytest.raises(e3.AssetError, match="only generate missing .png"):
        e3.Cube(texture=tmp_path / "texture.jpg", scene=scene)
    directory = tmp_path / "directory.png"
    directory.mkdir()
    with pytest.raises(e3.AssetError):
        e3.Cube(texture=directory, scene=scene)
    assert directory.is_dir()
    scene.close()


def test_generation_permission_failure_is_actionable_and_non_destructive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "denied" / "texture.png"
    original_open = Path.open

    def deny_target(candidate: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if candidate == path:
            raise PermissionError("test denied texture creation")
        return original_open(candidate, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "open", deny_target)
    scene = e3.Scene()
    with pytest.raises(e3.AssetError, match="could not generate texture"):
        e3.Cube(texture=path, scene=scene)
    assert not path.exists()
    assert not path.with_suffix(".texture.json").exists()
    scene.close()


def test_explicit_missing_normal_map_generates_a_matching_neutral_template(
    tmp_path: Path,
) -> None:
    scene = e3.Scene()
    base = tmp_path / "base.png"
    explicit = tmp_path / "normals" / "custom.png"
    cube = e3.Cube(texture=base, normal_map=explicit, scene=scene)
    renderer = cube.get_component(e3.MeshRenderer)

    assert renderer is not None
    assert renderer.normal_map == explicit.resolve()
    assert explicit.is_file()
    base_info = e3.load_image(base)
    normal_info = e3.load_image(explicit, color_space="linear")
    assert (normal_info.width, normal_info.height) == (
        base_info.width,
        base_info.height,
    )
    scene.close()


def test_generated_mapping_conflict_is_descriptive(tmp_path: Path) -> None:
    path = tmp_path / "shared.png"
    first = e3.Scene()
    e3.Cube(texture=path, texture_mode="tile", scene=first)
    first.close()

    second = e3.Scene()
    with pytest.raises(e3.AssetError, match="incompatible mapping"):
        e3.Cube(texture=path, texture_mode="atlas", scene=second)
    second.close()


def test_companion_discovery_disable_and_runtime_configuration(tmp_path: Path) -> None:
    path = tmp_path / "surface.png"
    scene = e3.Scene()
    cube = e3.Cube(texture=path, normal_map=False, scene=scene)
    renderer = cube.get_component(e3.MeshRenderer)
    assert renderer is not None
    assert renderer.normal_map is None

    renderer.normal_map = path.with_name("custom_normal.png")
    assert renderer.normal_map == path.with_name("custom_normal.png").resolve()
    renderer.normal_strength = 0
    assert renderer.normal_strength == 0
    renderer.normal_strength = 0.25
    renderer.pixels_per_unit = 24
    renderer.texture_filter = "linear"
    assert renderer.normal_strength == pytest.approx(0.25)
    assert renderer.pixels_per_unit == pytest.approx(24)
    assert renderer.texture_filter == "linear"
    renderer.texture = None
    assert renderer.texture is None
    assert renderer.normal_map is None
    scene.close()


def test_expanded_material_maps_are_retained(tmp_path: Path) -> None:
    base = tmp_path / "material.png"
    seed_scene = e3.Scene()
    e3.Cube(texture=base, scene=seed_scene)
    seed_scene.close()
    for suffix in ("roughness", "metallic", "emissive", "ao"):
        base.with_name(f"material_{suffix}.png").write_bytes(base.read_bytes())

    scene = e3.Scene()
    cube = e3.Cube(texture=base, scene=scene)
    renderer = cube.get_component(e3.MeshRenderer)
    assert renderer is not None
    assert renderer.normal_map == base.with_name("material_normal.png").resolve()
    assert renderer.roughness_map == base.with_name("material_roughness.png").resolve()
    assert renderer.metallic_map == base.with_name("material_metallic.png").resolve()
    assert renderer.emissive_map == base.with_name("material_emissive.png").resolve()
    assert renderer.ambient_occlusion_map == base.with_name("material_ao.png").resolve()
    assert renderer.roughness == pytest.approx(1)
    assert renderer.metallic == pytest.approx(1)
    assert renderer.emission == pytest.approx(1)

    explicit = e3.Cube(
        texture=base,
        roughness=0.75,
        metallic=0.25,
        emission=2,
        scene=scene,
    ).get_component(e3.MeshRenderer)
    assert explicit is not None
    assert explicit.roughness == pytest.approx(0.75)
    assert explicit.metallic == pytest.approx(0.25)
    assert explicit.emission == pytest.approx(2)

    replacement = tmp_path / "replacement.png"
    renderer.texture = replacement
    assert renderer.texture == replacement.resolve()
    assert renderer.normal_map == replacement.with_name("replacement_normal.png").resolve()
    assert renderer.roughness_map is None
    assert renderer.metallic_map is None
    assert renderer.emissive_map is None
    assert renderer.ambient_occlusion_map is None
    assert renderer.roughness == pytest.approx(0.5)
    assert renderer.metallic == pytest.approx(0)
    assert renderer.emission == pytest.approx(0)

    runtime_metallic = tmp_path / "runtime_metallic.png"
    runtime_metallic.write_bytes(replacement.read_bytes())
    renderer.metallic_map = runtime_metallic
    assert renderer.metallic == pytest.approx(1)
    renderer.metallic_map = False
    assert renderer.metallic_map is None
    assert renderer.metallic == pytest.approx(0)
    scene.close()


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("pixels_per_unit", 0),
        ("texture_filter", "blur"),
        ("texture_mode", "guess"),
        ("normal_strength", -1),
        ("metallic", 2),
        ("roughness", 0),
        ("emission", -1),
    ],
)
def test_texture_configuration_validation(
    tmp_path: Path, keyword: str, value: object
) -> None:
    scene = e3.Scene()
    with pytest.raises((TypeError, ValueError)):
        e3.Cube(texture=tmp_path / "bad.png", scene=scene, **{keyword: value})
    scene.close()


def test_texture_cache_hot_reload_and_invalid_save_recovery(tmp_path: Path) -> None:
    first = tmp_path / "reload.png"
    second = tmp_path / "replacement.png"
    scene = e3.Scene()
    e3.Cube(texture=first, scene=scene)
    e3.Sphere(texture=second, scene=scene)
    scene.close()

    cache = e3.TextureCache()
    assert cache.load(first).width == 16
    stamp = time.time_ns() + 2_000_000_000
    first.write_bytes(b"incomplete editor save")
    os.utime(first, ns=(stamp, stamp))
    assert cache.poll_changes() == 0
    assert cache.load(first).width == 16

    stamp += 2_000_000_000
    first.write_bytes(second.read_bytes())
    os.utime(first, ns=(stamp, stamp))
    assert cache.poll_changes() == 1
    assert cache.load(first).width == 32


def test_hot_reload_can_be_disabled(tmp_path: Path) -> None:
    first = tmp_path / "fixed.png"
    second = tmp_path / "larger.png"
    scene = e3.Scene()
    e3.Cube(texture=first, scene=scene)
    e3.Sphere(texture=second, scene=scene)
    scene.close()

    cache = e3.TextureCache()
    assert cache.load(first, hot_reload=False).width == 16
    stamp = time.time_ns() + 2_000_000_000
    first.write_bytes(second.read_bytes())
    os.utime(first, ns=(stamp, stamp))
    assert cache.poll_changes() == 0
    assert cache.load(first, hot_reload=False).width == 16


def test_texture_cache_reuses_canonical_path_and_color_space(tmp_path: Path) -> None:
    path = tmp_path / "shared.png"
    scene = e3.Scene()
    e3.Cube(texture=path, scene=scene)
    scene.close()

    cache = e3.TextureCache()
    for _ in range(100):
        cache.load(path)
        cache.load(path.parent / "." / path.name)
    assert len(cache) == 1
    cache.load(path, color_space="linear")
    assert len(cache) == 2


def test_obj_missing_material_texture_uses_authored_uv_template(tmp_path: Path) -> None:
    (tmp_path / "surface.mtl").write_text(
        "newmtl Surface\nmap_Kd generated/albedo.png\n", encoding="utf-8"
    )
    model = tmp_path / "surface.obj"
    model.write_text(
        "mtllib surface.mtl\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "vt 0 0\nvt 1 0\nvt 0 1\n"
        "usemtl Surface\nf 1/1 2/2 3/3\n",
        encoding="utf-8",
    )
    scene = e3.Scene()
    entity = e3.Model(model, scene=scene)
    generated = tmp_path / "generated" / "albedo.png"
    assert entity.is_alive
    assert generated.is_file()
    assert generated.with_name("albedo_normal.png").is_file()
    assert e3.load_image(generated).width == 256
    scene.close()


def test_obj_missing_texture_without_uvs_reports_limitation(tmp_path: Path) -> None:
    (tmp_path / "surface.mtl").write_text(
        "newmtl Surface\nmap_Kd missing.png\n", encoding="utf-8"
    )
    model = tmp_path / "surface.obj"
    model.write_text(
        "mtllib surface.mtl\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "usemtl Surface\nf 1 2 3\n",
        encoding="utf-8",
    )
    scene = e3.Scene()
    with pytest.raises(e3.AssetError, match="no usable UVs"):
        e3.Model(model, scene=scene)
    scene.close()


def test_gltf_missing_texture_with_authored_uvs_generates_template(tmp_path: Path) -> None:
    model = tmp_path / "triangle.gltf"
    model.write_text(
        json.dumps(
            {
                "asset": {"version": "2.0"},
                "buffers": [
                    {
                        "uri": (
                            "data:application/octet-stream;base64,"
                            "AACAvwAAAAAAAAAAAACAPwAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAIA/"
                            "AAAAAAAAAAAAAIA/AAAAAAAAAAAAAIA/AAAAAAAAAAAAAIA/AAAAAAAAAD8AAIA/"
                            "AAABAAIA"
                        ),
                        "byteLength": 102,
                    }
                ],
                "bufferViews": [
                    {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                    {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                    {"buffer": 0, "byteOffset": 72, "byteLength": 24},
                    {"buffer": 0, "byteOffset": 96, "byteLength": 6},
                ],
                "accessors": [
                    {
                        "bufferView": 0,
                        "componentType": 5126,
                        "count": 3,
                        "type": "VEC3",
                        "min": [-1, 0, 0],
                        "max": [1, 2, 0],
                    },
                    {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
                    {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
                    {"bufferView": 3, "componentType": 5123, "count": 3, "type": "SCALAR"},
                ],
                "images": [{"uri": "generated/albedo.png"}],
                "textures": [{"source": 0}],
                "materials": [
                    {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
                ],
                "meshes": [
                    {
                        "primitives": [
                            {
                                "attributes": {
                                    "POSITION": 0,
                                    "NORMAL": 1,
                                    "TEXCOORD_0": 2,
                                },
                                "indices": 3,
                                "material": 0,
                            }
                        ]
                    }
                ],
                "nodes": [{"mesh": 0}],
                "scenes": [{"nodes": [0]}],
                "scene": 0,
            }
        ),
        encoding="utf-8",
    )
    scene = e3.Scene()
    entity = e3.Model(model, scene=scene)
    generated = tmp_path / "generated" / "albedo.png"
    assert entity.is_alive
    assert e3.load_image(generated).width == 256
    assert generated.with_name("albedo_normal.png").is_file()
    scene.close()
