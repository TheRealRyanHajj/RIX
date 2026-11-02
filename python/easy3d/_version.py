"""Installed Easy3D distribution version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("easy3d")
except PackageNotFoundError:
    __version__ = "0+unknown"

