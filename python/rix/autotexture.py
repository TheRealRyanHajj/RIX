"""Deterministic missing-texture templates and material-map discovery.

The beginner-facing primitive constructors call this module before crossing the
native boundary. Existing files are never rewritten; generated files carry a
small sidecar so incompatible requests for the same filename fail loudly.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from functools import lru_cache
from os import PathLike
from pathlib import Path
from typing import Literal, TypeAlias, cast

from ._rix import AssetError

TextureFilter: TypeAlias = Literal["nearest", "linear"]
TextureMode: TypeAlias = Literal["auto", "tile", "atlas", "sphere", "preserve"]
TexturePath: TypeAlias = str | PathLike[str]
OptionalMap: TypeAlias = TexturePath | Literal[False] | None

_GENERATOR = "rix-autotexture-1"
_MAX_TEMPLATE_DIMENSION = 4096
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class PreparedTextures:
    texture: Path | None
    normal_map: Path | None
    roughness_map: Path | None
    metallic_map: Path | None
    emissive_map: Path | None
    ambient_occlusion_map: Path | None
    mode: TextureMode


def validate_pixels_per_unit(value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or not 0 < result <= 4096:
        raise ValueError("pixels_per_unit must be finite and in (0, 4096]")
    return result


def validate_texture_filter(value: str) -> TextureFilter:
    if value not in ("nearest", "linear"):
        raise ValueError("texture_filter must be 'nearest' or 'linear'")
    return cast(TextureFilter, value)


def validate_texture_mode(value: str) -> TextureMode:
    if value not in ("auto", "tile", "atlas", "sphere", "preserve"):
        raise ValueError(
            "texture_mode must be 'auto', 'tile', 'atlas', 'sphere', or 'preserve'"
        )
    return cast(TextureMode, value)


def _resolved_mode(kind: str, mode: TextureMode) -> TextureMode:
    if mode != "auto":
        return mode
    if kind in ("cube", "plane"):
        return "tile"
    if kind == "sphere":
        return "sphere"
    return "preserve"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _png_bytes(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA buffer size does not match the PNG dimensions")
    rows = b"".join(
        b"\0" + rgba[y * width * 4 : (y + 1) * width * 4]
        for y in range(height)
    )
    return (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )


def _write_new(path: Path, data: bytes) -> None:
    if path.suffix.lower() != ".png":
        raise AssetError(
            f"RIX can only generate missing .png textures, not '{path.suffix}'"
        )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        return
    except OSError as error:
        try:
            if path.exists() and path.stat().st_size == 0:
                path.unlink()
        except OSError:
            pass
        raise AssetError(f"could not generate texture '{path}': {error}") from error


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(".texture.json")


def _write_metadata(
    path: Path,
    metadata: dict[str, object],
    *,
    refresh_generated: bool = False,
) -> None:
    sidecar = _metadata_path(path)
    encoded = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    try:
        with sidecar.open("xb") as stream:
            stream.write(encoded)
    except FileExistsError:
        if not refresh_generated:
            return
        try:
            existing = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise AssetError(
                f"could not refresh generated texture metadata '{sidecar}': {error}"
            ) from error
        if not isinstance(existing, dict) or existing.get("generator") != _GENERATOR:
            return
        try:
            with sidecar.open("wb") as stream:
                stream.write(encoded)
        except OSError as error:
            raise AssetError(
                f"could not refresh generated texture metadata '{sidecar}': {error}"
            ) from error
    except OSError as error:
        raise AssetError(f"could not write texture metadata '{sidecar}': {error}") from error


@lru_cache(maxsize=1024)
def _cached_generated_metadata(sidecar_text: str, modified_ns: int) -> dict[str, object]:
    del modified_ns  # The timestamp is part of the cache key.
    sidecar = Path(sidecar_text)
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AssetError(f"invalid RIX texture metadata '{sidecar}': {error}") from error
    if not isinstance(value, dict):
        raise AssetError(f"invalid RIX texture metadata '{sidecar}': expected an object")
    return value


def _compatible_metadata(path: Path, requested: dict[str, object]) -> None:
    sidecar = _metadata_path(path)
    try:
        modified_ns = sidecar.stat().st_mtime_ns
    except FileNotFoundError:
        return
    except OSError as error:
        raise AssetError(f"could not inspect texture metadata '{sidecar}': {error}") from error
    existing = _cached_generated_metadata(str(sidecar), modified_ns)
    if existing.get("generator") != _GENERATOR:
        return
    keys = ["mapping", "layout"]
    conflicts = [key for key in keys if existing.get(key) != requested.get(key)]
    if existing.get("mapping") == "atlas" or requested.get("mapping") == "atlas":
        # Atlas compatibility is determined by normalized face regions, not
        # absolute pixel dimensions. Uniformly increasing pixels-per-unit
        # preserves the same layout, while a differently proportioned cuboid
        # would point faces at different regions and must be rejected.
        def normalized_faces(metadata: dict[str, object]) -> tuple[object, ...] | None:
            width = metadata.get("width")
            height = metadata.get("height")
            faces = metadata.get("faces")
            if (
                not isinstance(width, (int, float))
                or isinstance(width, bool)
                or not isinstance(height, (int, float))
                or isinstance(height, bool)
                or width <= 0
                or height <= 0
                or not isinstance(faces, dict)
            ):
                return None
            signature: list[object] = []
            for name in sorted(faces):
                rectangle = faces[name]
                if (
                    not isinstance(name, str)
                    or not isinstance(rectangle, list)
                    or len(rectangle) != 4
                    or any(
                        not isinstance(value, (int, float)) or isinstance(value, bool)
                        for value in rectangle
                    )
                ):
                    return None
                signature.append(name)
                signature.extend(
                    round(float(value) / (float(width) if index % 2 == 0 else float(height)), 9)
                    for index, value in enumerate(rectangle)
                )
            return tuple(signature)

        if normalized_faces(existing) != normalized_faces(requested):
            conflicts.append("face layout")
    if conflicts:
        raise AssetError(
            f"texture '{path}' was generated for an incompatible mapping "
            f"({', '.join(conflicts)} differ); choose a separate filename"
        )


def _tile_pixels(size: int) -> bytes:
    pixels = bytearray(size * size * 4)
    cell = max(2, size // 4)
    for y in range(size):
        for x in range(size):
            bright = ((x // cell) + (y // cell)) % 2 == 0
            color = (205, 74, 190, 255) if bright else (45, 45, 55, 255)
            offset = (y * size + x) * 4
            pixels[offset : offset + 4] = bytes(color)
    return bytes(pixels)


def _paint_rect(
    pixels: bytearray,
    image_width: int,
    left: int,
    top: int,
    width: int,
    height: int,
    color: tuple[int, int, int, int],
) -> None:
    for y in range(top, top + height):
        for x in range(left, left + width):
            border = x in (left, left + width - 1) or y in (top, top + height - 1)
            marker = x - left < max(1, width // 6) and y - top < max(1, height // 6)
            value = (255, 255, 255, 255) if marker else (
                (25, 25, 25, 255) if border else color
            )
            offset = (y * image_width + x) * 4
            pixels[offset : offset + 4] = bytes(value)


def _atlas_template(
    dimensions: tuple[float, float, float], pixels_per_unit: float
) -> tuple[int, int, bytes, dict[str, list[int]]]:
    width_units, height_units, depth_units = dimensions
    x = max(1, math.ceil(abs(width_units) * pixels_per_unit))
    y = max(1, math.ceil(abs(height_units) * pixels_per_unit))
    z = max(1, math.ceil(abs(depth_units) * pixels_per_unit))
    width = x * 2 + z * 2
    height = y + z * 2
    if width > _MAX_TEMPLATE_DIMENSION or height > _MAX_TEMPLATE_DIMENSION:
        raise AssetError(
            f"generated cube atlas would be {width}x{height}; maximum is "
            f"{_MAX_TEMPLATE_DIMENSION}x{_MAX_TEMPLATE_DIMENSION}"
        )
    pixels = bytearray(width * height * 4)
    faces = {
        "left": [0, z, z, y],
        "front": [z, z, x, y],
        "right": [z + x, z, z, y],
        "back": [z + x + z, z, x, y],
        "top": [z, 0, x, z],
        "bottom": [z, z + y, x, z],
    }
    colors = {
        "front": (220, 70, 70, 255),
        "back": (70, 190, 90, 255),
        "right": (70, 120, 230, 255),
        "left": (230, 190, 55, 255),
        "top": (180, 80, 220, 255),
        "bottom": (55, 200, 210, 255),
    }
    for name, rect in faces.items():
        left, top, face_width, face_height = rect
        _paint_rect(
            pixels,
            width,
            left,
            top,
            face_width,
            face_height,
            colors[name],
        )
    return width, height, bytes(pixels), faces


def _normal_pixels(width: int, height: int) -> bytes:
    return bytes((128, 128, 255, 255)) * (width * height)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    x0, y0 = start
    x1, y1 = end
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            offset = (y0 * width + x0) * 4
            pixels[offset : offset + 4] = b"\xff\xff\xff\xff"
        if x0 == x1 and y0 == y1:
            break
        doubled = error * 2
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def _write_model_template(
    texture: Path,
    model: Path,
    uvs: list[tuple[float, float]],
    triangles: list[tuple[int, int, int]],
) -> None:
    if not uvs or not triangles:
        raise AssetError(
            f"model '{model}' references missing texture '{texture}' but has no usable UVs"
        )
    size = 256
    pixels = bytearray((36, 42, 54, 80)) * (size * size)
    points = [
        (
            round(max(0.0, min(1.0, u)) * (size - 1)),
            round((1.0 - max(0.0, min(1.0, v))) * (size - 1)),
        )
        for u, v in uvs
    ]
    for triangle in triangles:
        a, b, c = (points[index] for index in triangle)
        _draw_line(pixels, size, size, a, b)
        _draw_line(pixels, size, size, b, c)
        _draw_line(pixels, size, size, c, a)
    _write_new(texture, _png_bytes(size, size, bytes(pixels)))
    metadata: dict[str, object] = {
        "generator": _GENERATOR,
        "mapping": "preserve",
        "layout": "authored-model-uv-v1",
        "source_model": str(model.resolve()),
        "width": size,
        "height": size,
    }
    _write_metadata(texture, metadata)
    normal = texture.with_name(f"{texture.stem}_normal.png")
    if not normal.exists():
        _write_new(normal, _png_bytes(size, size, _normal_pixels(size, size)))
        normal_metadata = dict(metadata)
        normal_metadata["data"] = "tangent-space-normal-directx"
        _write_metadata(normal, normal_metadata)


def _prepare_obj_textures(model: Path) -> None:
    try:
        lines = model.read_text(encoding="utf-8", errors="strict").splitlines()
    except OSError as error:
        raise AssetError(f"could not inspect OBJ '{model}': {error}") from error
    uvs: list[tuple[float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    libraries: list[Path] = []
    for line in lines:
        tokens = line.strip().split()
        if not tokens or tokens[0].startswith("#"):
            continue
        if tokens[0] == "vt" and len(tokens) >= 3:
            try:
                uvs.append((float(tokens[1]), float(tokens[2])))
            except ValueError:
                continue
        elif tokens[0] == "mtllib" and len(tokens) >= 2:
            libraries.extend(model.parent / name for name in tokens[1:])
        elif tokens[0] == "f" and len(tokens) >= 4:
            indices: list[int] = []
            for token in tokens[1:]:
                fields = token.split("/")
                if len(fields) < 2 or not fields[1]:
                    indices = []
                    break
                try:
                    raw = int(fields[1])
                except ValueError:
                    indices = []
                    break
                index = raw - 1 if raw > 0 else len(uvs) + raw
                if not 0 <= index < len(uvs):
                    indices = []
                    break
                indices.append(index)
            for corner in range(1, len(indices) - 1):
                triangles.append((indices[0], indices[corner], indices[corner + 1]))
    for library in libraries:
        if not library.is_file():
            continue
        try:
            material_lines = library.read_text(encoding="utf-8", errors="strict").splitlines()
        except OSError:
            continue
        for line in material_lines:
            tokens = line.strip().split()
            if len(tokens) < 2 or tokens[0].lower() != "map_kd":
                continue
            texture = Path(tokens[-1])
            if not texture.is_absolute():
                texture = library.parent / texture
            if not texture.exists():
                _write_model_template(texture, model, uvs, triangles)


def _prepare_gltf_textures(model: Path) -> None:
    try:
        document = json.loads(model.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise AssetError(f"could not inspect glTF '{model}': {error}") from error
    has_uvs = any(
        "TEXCOORD_0" in primitive.get("attributes", {})
        for mesh in document.get("meshes", [])
        for primitive in mesh.get("primitives", [])
    )
    texture_indices = {
        material.get("pbrMetallicRoughness", {})
        .get("baseColorTexture", {})
        .get("index")
        for material in document.get("materials", [])
    }
    textures = document.get("textures", [])
    images = document.get("images", [])
    for texture_index in texture_indices:
        if not isinstance(texture_index, int) or not 0 <= texture_index < len(textures):
            continue
        image_index = textures[texture_index].get("source")
        if not isinstance(image_index, int) or not 0 <= image_index < len(images):
            continue
        uri = images[image_index].get("uri")
        if not isinstance(uri, str) or uri.startswith("data:"):
            continue
        texture = model.parent / uri
        if texture.exists():
            continue
        if not has_uvs:
            raise AssetError(
                f"glTF '{model}' references missing texture '{texture}' without TEXCOORD_0"
            )
        size = 256
        metadata = {
            "generator": _GENERATOR,
            "mapping": "preserve",
            "layout": "gltf-authored-uv-grid-v1",
            "source_model": str(model.resolve()),
            "width": size,
            "height": size,
        }
        _write_new(texture, _png_bytes(size, size, _tile_pixels(size)))
        _write_metadata(texture, metadata)
        normal = texture.with_name(f"{texture.stem}_normal.png")
        if not normal.exists():
            _write_new(normal, _png_bytes(size, size, _normal_pixels(size, size)))


def prepare_model_textures(path: TexturePath) -> None:
    """Generate missing authored-UV base textures for inspectable model formats."""

    model = Path(path)
    suffix = model.suffix.lower()
    if suffix == ".obj":
        _prepare_obj_textures(model)
    elif suffix == ".gltf":
        _prepare_gltf_textures(model)


def _generate_pair(
    path: Path,
    kind: str,
    mode: TextureMode,
    dimensions: tuple[float, float, float],
    pixels_per_unit: float,
) -> Path:
    if mode == "atlas" and kind != "cube":
        raise AssetError("atlas texture generation is currently supported for cubes only")
    faces: dict[str, list[int]] | None = None
    if mode == "atlas":
        width, height, pixels, faces = _atlas_template(dimensions, pixels_per_unit)
        layout = "rix-cube-cross-v1"
    else:
        base = max(16, min(256, math.ceil(pixels_per_unit)))
        width = base * 2 if mode == "sphere" else base
        height = base
        pixels = _tile_pixels(base)
        if width != base:
            pixels = b"".join(
                pixels[y * base * 4 : (y + 1) * base * 4] * 2
                for y in range(base)
            )
        layout = "rix-spherical-v1" if mode == "sphere" else "rix-tile-v1"
    metadata: dict[str, object] = {
        "generator": _GENERATOR,
        "mapping": mode,
        "layout": layout,
        "pixels_per_unit": pixels_per_unit,
        "width": width,
        "height": height,
    }
    if faces is not None:
        metadata["faces"] = faces
    if path.exists():
        _compatible_metadata(path, metadata)
        return path
    normal = path.with_name(f"{path.stem}_normal.png")
    normal_metadata = dict(metadata)
    normal_metadata["data"] = "tangent-space-normal-directx"
    # A retained generator sidecar is authoritative even if its image was
    # deleted. Validate every file identity before creating either PNG so an
    # incompatible request cannot leave a partially regenerated pair.
    if _metadata_path(path).is_file():
        _compatible_metadata(path, metadata)
    if not normal.exists() and _metadata_path(normal).is_file():
        _compatible_metadata(normal, normal_metadata)
    _write_new(path, _png_bytes(width, height, pixels))
    _write_metadata(path, metadata, refresh_generated=True)
    if not normal.exists():
        _write_new(normal, _png_bytes(width, height, _normal_pixels(width, height)))
        _write_metadata(normal, normal_metadata, refresh_generated=True)
    return path


@lru_cache(maxsize=1024)
def _cached_companions(
    texture_text: str, directory_modified_ns: int
) -> tuple[Path | None, Path | None, Path | None, Path | None, Path | None]:
    del directory_modified_ns  # The timestamp is part of the cache key.
    texture = Path(texture_text)
    candidates = tuple(
        texture.with_name(f"{texture.stem}_{suffix}.png")
        for suffix in ("normal", "roughness", "metallic", "emissive", "ao")
    )
    return tuple(candidate if candidate.is_file() else None for candidate in candidates)  # type: ignore[return-value]


def _discover_companions(texture: Path) -> dict[str, Path | None]:
    try:
        modified_ns = texture.parent.stat().st_mtime_ns
    except OSError:
        modified_ns = 0
    values = _cached_companions(str(texture), modified_ns)
    return dict(zip(("normal", "roughness", "metallic", "emissive", "ao"), values, strict=True))


def _explicit_map(
    value: OptionalMap,
    texture: Path,
    suffix: str,
    companions: dict[str, Path | None],
) -> Path | None:
    if value is False:
        return None
    if value is None:
        return companions[suffix]
    if value is True:  # type: ignore[comparison-overlap]
        raise TypeError(f"{suffix}_map must be a path, False, or None")
    return Path(value)


def _prepare_textures_uncached(
    texture: TexturePath | None,
    *,
    kind: str,
    dimensions: tuple[float, float, float],
    pixels_per_unit: float,
    texture_mode: TextureMode,
    normal_map: OptionalMap = None,
    roughness_map: OptionalMap = None,
    metallic_map: OptionalMap = None,
    emissive_map: OptionalMap = None,
    ambient_occlusion_map: OptionalMap = None,
) -> PreparedTextures:
    """Prepare one primitive's texture paths without overwriting user assets."""

    mode = _resolved_mode(kind, validate_texture_mode(texture_mode))
    density = validate_pixels_per_unit(pixels_per_unit)
    if texture is None:
        requested_maps = (
            normal_map,
            roughness_map,
            metallic_map,
            emissive_map,
            ambient_occlusion_map,
        )
        if any(value not in (None, False) for value in requested_maps):
            raise ValueError("material maps require a base texture")
        return PreparedTextures(None, None, None, None, None, None, mode)

    path = Path(texture)
    if not path.exists() or _metadata_path(path).is_file():
        _generate_pair(path, kind, mode, dimensions, density)
    companions = _discover_companions(path)
    normal = _explicit_map(normal_map, path, "normal", companions)
    if normal is not None and not normal.exists():
        # An explicitly requested missing normal is safe to generate because
        # the base texture establishes the exact compatible dimensions.
        from .assets import load_image

        info = load_image(path)
        _write_new(normal, _png_bytes(info.width, info.height, _normal_pixels(info.width, info.height)))
    return PreparedTextures(
        path,
        normal,
        _explicit_map(roughness_map, path, "roughness", companions),
        _explicit_map(metallic_map, path, "metallic", companions),
        _explicit_map(emissive_map, path, "emissive", companions),
        _explicit_map(ambient_occlusion_map, path, "ao", companions),
        mode,
    )


@lru_cache(maxsize=2048)
def _prepare_textures_cached(
    texture: str,
    kind: str,
    dimensions: tuple[float, float, float],
    pixels_per_unit: float,
    texture_mode: TextureMode,
    normal_map: str | Literal[False] | None,
    roughness_map: str | Literal[False] | None,
    metallic_map: str | Literal[False] | None,
    emissive_map: str | Literal[False] | None,
    ambient_occlusion_map: str | Literal[False] | None,
    directory_modified_ns: int,
    metadata_modified_ns: int,
) -> PreparedTextures:
    del directory_modified_ns, metadata_modified_ns  # Filesystem stamps are cache keys.
    return _prepare_textures_uncached(
        texture,
        kind=kind,
        dimensions=dimensions,
        pixels_per_unit=pixels_per_unit,
        texture_mode=texture_mode,
        normal_map=normal_map,
        roughness_map=roughness_map,
        metallic_map=metallic_map,
        emissive_map=emissive_map,
        ambient_occlusion_map=ambient_occlusion_map,
    )


def prepare_textures(
    texture: TexturePath | None,
    *,
    kind: str,
    dimensions: tuple[float, float, float],
    pixels_per_unit: float,
    texture_mode: TextureMode,
    normal_map: OptionalMap = None,
    roughness_map: OptionalMap = None,
    metallic_map: OptionalMap = None,
    emissive_map: OptionalMap = None,
    ambient_occlusion_map: OptionalMap = None,
) -> PreparedTextures:
    """Prepare material paths, coalescing repeated filesystem discovery briefly."""

    if texture is None:
        return _prepare_textures_uncached(
            None,
            kind=kind,
            dimensions=dimensions,
            pixels_per_unit=pixels_per_unit,
            texture_mode=texture_mode,
            normal_map=normal_map,
            roughness_map=roughness_map,
            metallic_map=metallic_map,
            emissive_map=emissive_map,
            ambient_occlusion_map=ambient_occlusion_map,
        )

    def map_key(value: OptionalMap) -> str | Literal[False] | None:
        if value is None or value is False:
            return value
        return str(Path(value))

    path = Path(texture)
    try:
        directory_modified_ns = path.parent.stat().st_mtime_ns
    except OSError:
        directory_modified_ns = 0
    try:
        metadata_modified_ns = _metadata_path(path).stat().st_mtime_ns
    except OSError:
        metadata_modified_ns = 0
    return _prepare_textures_cached(
        str(path),
        kind,
        (float(dimensions[0]), float(dimensions[1]), float(dimensions[2])),
        float(pixels_per_unit),
        validate_texture_mode(texture_mode),
        map_key(normal_map),
        map_key(roughness_map),
        map_key(metallic_map),
        map_key(emissive_map),
        map_key(ambient_occlusion_map),
        directory_modified_ns,
        metadata_modified_ns,
    )


__all__ = ["TextureFilter", "TextureMode"]
