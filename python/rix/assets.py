"""Texture asset loading and shared CPU image caching."""

from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
import math
from os import PathLike
from pathlib import Path
from typing import Literal, TypeAlias

from ._rix import (
    _ModelCache,
    _TextureCache,
    _TextureColorSpace,
    _load_image_info,
    _load_gltf_info,
    _load_obj_info,
)
from .math import Quat, Vec3

ColorSpace: TypeAlias = Literal["srgb", "linear"]


def _native_color_space(value: ColorSpace) -> _TextureColorSpace:
    if value == "srgb":
        return _TextureColorSpace.SRGB
    if value == "linear":
        return _TextureColorSpace.LINEAR
    raise ValueError("color_space must be 'srgb' or 'linear'")


@dataclass(frozen=True, slots=True)
class ImageInfo:
    """Immutable metadata for a native RGBA8 image resource."""

    path: Path
    width: int
    height: int
    byte_size: int
    color_space: ColorSpace


def _to_info(value: tuple[str, int, int, int, bool]) -> ImageInfo:
    path, width, height, byte_size, is_srgb = value
    return ImageInfo(
        Path(path), width, height, byte_size, "srgb" if is_srgb else "linear"
    )


def load_image(
    path: str | PathLike[str], *, color_space: ColorSpace = "srgb"
) -> ImageInfo:
    """Decode a PNG/JPEG to native RGBA8 storage and return its metadata."""

    return _to_info(_load_image_info(str(path), _native_color_space(color_space)))


class TextureCache:
    """Thread-safe cache keyed by canonical path and color space."""

    __slots__ = ("_native",)

    def __init__(self) -> None:
        self._native = _TextureCache()

    def load(
        self,
        path: str | PathLike[str],
        *,
        color_space: ColorSpace = "srgb",
        hot_reload: bool = True,
    ) -> ImageInfo:
        if not isinstance(hot_reload, bool):
            raise TypeError("hot_reload must be a bool")
        return _to_info(
            self._native.load(str(path), _native_color_space(color_space), hot_reload)
        )

    def poll_changes(self) -> int:
        """Reload changed files and return the number of valid replacements."""

        return self._native.poll_changes(0)

    def clear(self) -> None:
        self._native.clear()

    def __len__(self) -> int:
        return self._native.size


@dataclass(frozen=True, slots=True)
class ModelMaterialInfo:
    name: str
    diffuse_color: tuple[float, float, float, float]
    diffuse_texture: Path | None
    metallic: float = 0.0
    roughness: float = 0.5
    emission: float = 0.0
    normal_texture: Path | None = None
    roughness_texture: Path | None = None
    metallic_texture: Path | None = None
    emissive_texture: Path | None = None
    ambient_occlusion_texture: Path | None = None
    normal_strength: float = 1.0
    packed_metallic_roughness: bool = False
    double_sided: bool = False


@dataclass(frozen=True, slots=True)
class ModelPartInfo:
    name: str
    vertex_count: int
    index_count: int
    triangle_count: int
    material_index: int


@dataclass(frozen=True, slots=True)
class ModelInfo:
    path: Path
    triangle_count: int
    parts: tuple[ModelPartInfo, ...]
    materials: tuple[ModelMaterialInfo, ...]
    warnings: tuple[str, ...]


def _to_model_info(
    value: tuple[
        str,
        int,
        list[tuple[str, int, int, int, int]],
        list[
            tuple[
                str,
                tuple[float, float, float, float],
                str | None,
                float,
                float,
                float,
                str | None,
                str | None,
                str | None,
                str | None,
                str | None,
                float,
                bool,
                bool,
            ]
        ],
        list[str],
    ],
) -> ModelInfo:
    path, triangle_count, native_parts, native_materials, warnings = value
    return ModelInfo(
        path=Path(path),
        triangle_count=triangle_count,
        parts=tuple(ModelPartInfo(*part) for part in native_parts),
        materials=tuple(
            ModelMaterialInfo(
                name,
                color,
                Path(texture) if texture else None,
                metallic,
                roughness,
                emission,
                Path(normal) if normal else None,
                Path(roughness_texture) if roughness_texture else None,
                Path(metallic_texture) if metallic_texture else None,
                Path(emissive) if emissive else None,
                Path(ao) if ao else None,
                normal_strength,
                packed,
                double_sided,
            )
            for (
                name,
                color,
                texture,
                metallic,
                roughness,
                emission,
                normal,
                roughness_texture,
                metallic_texture,
                emissive,
                ao,
                normal_strength,
                packed,
                double_sided,
            ) in native_materials
        ),
        warnings=tuple(warnings),
    )


def load_obj(path: str | PathLike[str]) -> ModelInfo:
    """Load and triangulate an OBJ/MTL asset into a shared native model."""

    return _to_model_info(_load_obj_info(str(path)))


@dataclass(frozen=True, slots=True)
class SkeletonJointInfo:
    name: str
    parent: int | None
    bind_position: Vec3
    bind_rotation: Quat
    bind_scale: Vec3
    inverse_bind: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SkeletonInfo:
    name: str
    joints: tuple[SkeletonJointInfo, ...]


@dataclass(frozen=True, slots=True)
class JointPose:
    position: Vec3
    rotation: Quat
    scale: Vec3


@dataclass(frozen=True, slots=True)
class AnimationChannelInfo:
    joint_index: int
    target: Literal["translation", "rotation", "scale"]
    interpolation: Literal["linear", "step"]
    times: tuple[float, ...]
    values: tuple[tuple[float, float, float, float], ...]


def _slerp(left: Quat, right: Quat, amount: float) -> Quat:
    cosine = sum(a * b for a, b in zip(left, right, strict=True))
    if cosine < 0:
        right = Quat(-right.w, -right.x, -right.y, -right.z)
        cosine = -cosine
    if cosine > 0.9995:
        return Quat(
            left.w + (right.w - left.w) * amount,
            left.x + (right.x - left.x) * amount,
            left.y + (right.y - left.y) * amount,
            left.z + (right.z - left.z) * amount,
        ).normalized()
    angle = math.acos(max(-1.0, min(1.0, cosine)))
    sine = math.sin(angle)
    first = math.sin((1.0 - amount) * angle) / sine
    second = math.sin(amount * angle) / sine
    return Quat(
        left.w * first + right.w * second,
        left.x * first + right.x * second,
        left.y * first + right.y * second,
        left.z * first + right.z * second,
    ).normalized()


@dataclass(frozen=True, slots=True)
class AnimationClipInfo:
    name: str
    duration: float
    channels: tuple[AnimationChannelInfo, ...]

    def sample(
        self, skeleton: SkeletonInfo, time_seconds: float, *, loop: bool = True
    ) -> tuple[JointPose, ...]:
        """Sample local joint transforms without mutating a scene or renderer."""

        if isinstance(time_seconds, bool) or not isinstance(time_seconds, (int, float)):
            raise TypeError("time_seconds must be a number")
        time_value = float(time_seconds)
        if not math.isfinite(time_value) or time_value < 0:
            raise ValueError("time_seconds must be finite and non-negative")
        if not isinstance(loop, bool):
            raise TypeError("loop must be bool")
        sample_time = time_value
        if self.duration > 0:
            sample_time = time_value % self.duration if loop else min(
                time_value, self.duration
            )
        pose = [
            JointPose(
                Vec3.from_value(joint.bind_position),
                Quat(joint.bind_rotation),
                Vec3.from_value(joint.bind_scale),
            )
            for joint in skeleton.joints
        ]
        for channel in self.channels:
            upper = bisect_right(channel.times, sample_time)
            if upper == 0:
                first = second = 0
            elif upper == len(channel.times):
                first = second = len(channel.times) - 1
            else:
                first, second = upper - 1, upper
            amount = 0.0
            if first != second and channel.interpolation == "linear":
                amount = (sample_time - channel.times[first]) / (
                    channel.times[second] - channel.times[first]
                )
            left, right = channel.values[first], channel.values[second]
            current = pose[channel.joint_index]
            if channel.target == "rotation":
                rotation = _slerp(Quat(left), Quat(right), amount)
                pose[channel.joint_index] = JointPose(
                    current.position, rotation, current.scale
                )
                continue
            value = Vec3(
                left[0] + (right[0] - left[0]) * amount,
                left[1] + (right[1] - left[1]) * amount,
                left[2] + (right[2] - left[2]) * amount,
            )
            pose[channel.joint_index] = JointPose(
                value if channel.target == "translation" else current.position,
                current.rotation,
                value if channel.target == "scale" else current.scale,
            )
        return tuple(pose)


@dataclass(frozen=True, slots=True)
class GltfInfo:
    path: Path
    triangle_count: int
    parts: tuple[ModelPartInfo, ...]
    materials: tuple[ModelMaterialInfo, ...]
    warnings: tuple[str, ...]
    skeleton: SkeletonInfo | None
    animations: tuple[AnimationClipInfo, ...]


def load_gltf(path: str | PathLike[str]) -> GltfInfo:
    """Load bounded glTF 2.0/GLB geometry, skeleton, and animation metadata."""

    native_model, native_skeleton, native_animations = _load_gltf_info(str(path))
    model = _to_model_info(native_model)
    skeleton = None
    if native_skeleton is not None:
        name, native_joints = native_skeleton
        skeleton = SkeletonInfo(
            name,
            tuple(
                SkeletonJointInfo(
                    joint_name,
                    None if parent < 0 else parent,
                    Vec3(position),
                    Quat(rotation),
                    Vec3(scale),
                    tuple(inverse_bind),
                )
                for joint_name, parent, position, rotation, scale, inverse_bind in native_joints
            ),
        )
    animations = tuple(
        AnimationClipInfo(
            name,
            duration,
            tuple(
                AnimationChannelInfo(
                    joint_index,
                    target,
                    interpolation,
                    tuple(times),
                    tuple(tuple(value) for value in values),
                )
                for joint_index, target, interpolation, times, values in native_channels
            ),
        )
        for name, duration, native_channels in native_animations
    )
    return GltfInfo(
        model.path,
        model.triangle_count,
        model.parts,
        model.materials,
        model.warnings,
        skeleton,
        animations,
    )


class ModelCache:
    """Thread-safe immutable OBJ/glTF/GLB model cache keyed by canonical path."""

    __slots__ = ("_native",)

    def __init__(self) -> None:
        self._native = _ModelCache()

    def load(self, path: str | PathLike[str]) -> ModelInfo:
        return _to_model_info(self._native.load(str(path)))

    def clear(self) -> None:
        self._native.clear()

    def __len__(self) -> int:
        return self._native.size
