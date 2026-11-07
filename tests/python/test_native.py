from __future__ import annotations

from importlib.metadata import version

import rix
import pytest
from rix import _rix


def test_version_is_native_and_matches_package() -> None:
    assert rix.engine_version() == rix.__version__ == version("rix") == "0.1.0"


@pytest.mark.parametrize(("left", "right", "expected"), [(1, 2, 3), (-4, 6, 2)])
def test_native_add(left: int, right: int, expected: int) -> None:
    assert rix.native_add(left, right) == expected


def test_registered_native_exception_translation() -> None:
    with pytest.raises(rix.EngineError, match=r"translated from C\+\+"):
        _rix._raise_engine_error("translated from C++")

