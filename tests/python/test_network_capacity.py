from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _benchmark_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "benchmarks" / "network_capacity.py"
    spec = importlib.util.spec_from_file_location("rix_network_capacity", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_eight_client_capacity_smoke_is_correct_and_bounded() -> None:
    report = _benchmark_module().run_capacity(8, ticks=20, warmup_ticks=5)
    assert report.correct
    assert report.transform_frames_queued > 0
    assert report.transform_frames_budget_deferred == 0
    assert report.tick_p99_ms > 0
    assert report.server_bytes_sent > 0
    assert report.client_bytes_received > 0
    assert report.transform_snapshot_bytes > 0
    assert report.transform_snapshot_mean_bytes > 0
    assert report.transform_full_snapshots + report.transform_delta_snapshots == (
        report.transform_frames_queued
    )
    assert report.transport_messages_lost == 0
    assert report.transport_queue_rejections == 0
    assert report.transport_event_overflows == 0
    assert report.transform_frames_backpressured == 0
    assert not _benchmark_module().budget_failures(report)


def test_capacity_arguments_are_bounded() -> None:
    run = _benchmark_module().run_capacity
    with pytest.raises(ValueError, match="2, 8, 16, or 32"):
        run(4)
    with pytest.raises(ValueError, match="at least 10"):
        run(8, ticks=9)


def test_capacity_budget_reports_specific_failures() -> None:
    module = _benchmark_module()
    report = module.CapacityReport(
        32, 10, False, 1.0, 1.0, 101.0, 101.0, 1.0, 51.0,
        1.0, 1.0, 201.0, 1, 129 * 1024 * 1024, 1, 900_000,
        1, 1.0, 1.0, 1, 1,
    )
    failures = module.budget_failures(report)
    assert any("incorrect" in failure for failure in failures)
    assert any("budget-deferred" in failure for failure in failures)
    assert any("tick p99" in failure for failure in failures)
    assert any("server bytes per tick" in failure for failure in failures)
