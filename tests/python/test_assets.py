from __future__ import annotations

import base64
from pathlib import Path

import pytest

from rix import AssetError, MissingAssetError
from rix.assets import TextureCache, load_image


PNG_2X2 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAAXNSR0IArs4c6QAAAARn"
    "QU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAAXSURBVBhXY/jPwPCfoYHh"
    "PwMDw38wAABD1Al4TlSdlQAAAABJRU5ErkJggg=="
)
JPEG_2X2 = (
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYI"
    "DAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkF"
    "BQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
    "FBQUFBT/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQF"
    "BgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEI"
    "I0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNk"
    "ZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLD"
    "xMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEB"
    "AQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB"
    "UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH"
    "SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaan"
    "qKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oA"
    "DAMBAAIRAxEAPwD7V/Z2+C3w91v9n74ZajqPgTwzf6heeF9MuLm7utHt5JZ5XtImd3dkJ"
    "ZmJJJJySSTRRRXyOL/3ip/if5nwmO/3qr/il+bP/9k="
)


def _write_base64(path: Path, encoded: str) -> None:
    path.write_bytes(base64.b64decode(encoded))


def test_png_jpeg_decode_and_color_space(tmp_path: Path) -> None:
    png = tmp_path / "pixel.png"
    jpeg = tmp_path / "colors.jpeg"
    _write_base64(png, PNG_2X2)
    _write_base64(jpeg, JPEG_2X2)

    png_info = load_image(png)
    jpeg_info = load_image(jpeg, color_space="linear")

    assert (png_info.width, png_info.height, png_info.byte_size) == (2, 2, 16)
    assert png_info.color_space == "srgb"
    assert (jpeg_info.width, jpeg_info.height, jpeg_info.byte_size) == (2, 2, 16)
    assert jpeg_info.color_space == "linear"


def test_cache_keys_and_errors(tmp_path: Path) -> None:
    png = tmp_path / "pixel.png"
    _write_base64(png, PNG_2X2)
    cache = TextureCache()

    cache.load(png)
    cache.load(png)
    cache.load(png, color_space="linear")
    assert len(cache) == 2
    cache.clear()
    assert len(cache) == 0

    with pytest.raises(MissingAssetError, match="missing.png"):
        cache.load(tmp_path / "missing.png")
    unsupported = tmp_path / "pixel.bmp"
    unsupported.write_bytes(base64.b64decode(PNG_2X2))
    with pytest.raises(AssetError, match="unsupported texture format"):
        load_image(unsupported)
    with pytest.raises(ValueError, match="color_space"):
        load_image(png, color_space="bad")  # type: ignore[arg-type]
