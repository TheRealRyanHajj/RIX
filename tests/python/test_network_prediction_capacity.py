from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _benchmark_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "benchmarks" / "network_prediction.py"
    spec = importlib.util.spec_from_file_location("rix_network_prediction", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prediction_capacity_reports_real_corrections_and_replays() -> None:
    report = _benchmark_module().run_prediction_capacity(
        8,
        ticks=30,
        correction_interval_ticks=3,
        correction_delay_ticks=6,
        warmup_ticks=5,
    )
    assert report.correct
    assert report.inputs_submitted == 240
    assert report.corrections_applied == 80
    assert report.corrections_per_client_per_second == pytest.approx(20.0)
    assert report.replayed_inputs > 0
    assert report.mean_replays_per_correction > 0
    assert report.maximum_position_error > 0
    assert report.tick_p99_ms > 0


def test_prediction_capacity_arguments_are_bounded() -> None:
    run = _benchmark_module().run_prediction_capacity
    with pytest.raises(ValueError, match="2, 8, 16, or 32"):
        run(4)
    with pytest.raises(ValueError, match="at least 10"):
        run(2, ticks=9)
    with pytest.raises(ValueError, match="positive"):
        run(2, correction_interval_ticks=0)
