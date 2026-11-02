from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _sample_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "examples" / "07_coop_sandbox" / "main.py"
    spec = importlib.util.spec_from_file_location("easy3d_coop_sandbox", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("clients", (2, 4, 8))
def test_cooperative_sandbox_real_loopback(clients: int) -> None:
    result = _sample_module().run_sandbox(clients)
    assert result.clients == clients
    assert result.players == clients
    assert result.synchronized_positions == clients * clients
    assert result.crate_destroyed
    assert result.rpc_executed == clients + 2


def test_cooperative_sandbox_client_bounds() -> None:
    run = _sample_module().run_sandbox
    with pytest.raises(ValueError, match=r"\[2, 8\]"):
        run(1)
    with pytest.raises(ValueError, match=r"\[2, 8\]"):
        run(9)
