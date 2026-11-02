from __future__ import annotations

from importlib.metadata import version

import easy3d
import pytest
from easy3d import _easy3d


def test_version_is_native_and_matches_package() -> None:
    assert easy3d.engine_version() == easy3d.__version__ == version("easy3d") == "0.1.0"


@pytest.mark.parametrize(("left", "right", "expected"), [(1, 2, 3), (-4, 6, 2)])
def test_native_add(left: int, right: int, expected: int) -> None:
    assert easy3d.native_add(left, right) == expected


def test_registered_native_exception_translation() -> None:
    with pytest.raises(easy3d.EngineError, match=r"translated from C\+\+"):
        _easy3d._raise_engine_error("translated from C++")

