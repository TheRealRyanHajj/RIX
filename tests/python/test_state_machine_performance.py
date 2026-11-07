from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "benchmarks" / "state_machine.py"
    spec = importlib.util.spec_from_file_location("rix_state_machine_benchmark", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_state_machine_benchmark_is_finite_and_correct() -> None:
    report = _module().run_benchmark(20_000, 4_000)
    assert report.correct
    assert report.update_nanoseconds > 0
    assert report.transition_nanoseconds > 0
    assert report.peak_bytes >= 0


def test_state_machine_benchmark_rejects_invalid_counts() -> None:
    run = _module().run_benchmark
    with pytest.raises(ValueError, match="updates"):
        run(0, 1)
    with pytest.raises(ValueError, match="transitions"):
        run(1, 0)
