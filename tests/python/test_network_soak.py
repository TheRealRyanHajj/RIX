from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from easy3d import network


def _soak_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "benchmarks" / "network_soak.py"
    spec = importlib.util.spec_from_file_location("easy3d_network_soak", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reconnect_spam_loss_and_shutdown_soak() -> None:
    report = _soak_module().run_soak(
        2,
        cycles=2,
        inputs_per_client=24,
        profile=network.ADVERSE_NETWORK_CONDITION,
    )
    assert report.correct
    assert report.inputs_sent == report.inputs_received
    assert report.inputs_rate_limited > 0
    assert report.reconnects_completed == 2
    assert report.shutdown_disconnects_observed == 2


def test_soak_arguments_are_bounded() -> None:
    run = _soak_module().run_soak
    with pytest.raises(ValueError, match=r"\[2, 32\]"):
        run(1)
    with pytest.raises(ValueError, match="positive"):
        run(2, cycles=0)
    with pytest.raises(ValueError, match=r"\[17, 1000\]"):
        run(2, inputs_per_client=16)
