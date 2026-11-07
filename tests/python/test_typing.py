from __future__ import annotations

from pathlib import Path
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[2]


def _run(*arguments: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", *arguments],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_documented_public_api_typechecks_strictly() -> None:
    _run("mypy")


def test_native_runtime_matches_extension_stub() -> None:
    _run(
        "mypy.stubtest",
        "rix._rix",
        "--allowlist",
        "tests/typecheck/stubtest_allowlist.txt",
    )
