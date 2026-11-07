"""Installed RIX distribution version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rix")
except PackageNotFoundError:
    __version__ = "0+unknown"

