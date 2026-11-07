"""Deprecated compatibility facade for the renamed :mod:`rix` package."""

from __future__ import annotations

import importlib
import sys
import warnings

warnings.warn(
    "easy3d was renamed to rix; replace 'import easy3d' with 'import rix'",
    DeprecationWarning,
    stacklevel=2,
)

import rix as _rix_package
from rix import *  # noqa: F401,F403

__all__ = _rix_package.__all__
__version__ = _rix_package.__version__

_FORWARDED_MODULES = (
    "_rix",
    "advanced",
    "assets",
    "audio",
    "autotexture",
    "camera",
    "components",
    "debug",
    "diagnostics",
    "entity",
    "game",
    "gameplay",
    "input",
    "lights",
    "math",
    "physics",
    "player",
    "primitives",
    "scene",
    "scheduler",
    "skybox",
    "time",
    "ui",
    "utilities",
    "world",
)

for _module_name in _FORWARDED_MODULES:
    _forwarded_module = importlib.import_module(f"rix.{_module_name}")
    sys.modules[f"{__name__}.{_module_name}"] = _forwarded_module
    setattr(sys.modules[__name__], _module_name, _forwarded_module)

# Preserve the most common legacy native import without shipping a second .pyd.
sys.modules[f"{__name__}._easy3d"] = sys.modules["rix._rix"]
_easy3d = sys.modules["rix._rix"]

del _forwarded_module, _module_name
