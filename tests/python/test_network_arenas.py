from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from easy3d import MatchPhase


def _sample_module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "examples" / "08_network_arenas" / "main.py"
    spec = importlib.util.spec_from_file_location("easy3d_network_arenas", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("clients", (2, 4, 8))
def test_cooperative_arena_authority(clients: int) -> None:
    result = _sample_module().run_arena("cooperative", clients)
    assert result.phase is MatchPhase.MATCH_END
    assert result.clients == clients
    assert result.winning_score == 1
    assert result.damage_events == 4
    assert result.objective_destroyed
    assert result.eliminated_players == 0


@pytest.mark.parametrize("clients", (2, 4, 8))
def test_competitive_arena_authority(clients: int) -> None:
    result = _sample_module().run_arena("competitive", clients)
    assert result.phase is MatchPhase.MATCH_END
    assert result.clients == clients
    assert result.winning_score == 1
    assert result.damage_events == 4
    assert not result.objective_destroyed
    assert result.eliminated_players == 1


def test_arena_bounds() -> None:
    run = _sample_module().run_arena
    with pytest.raises(ValueError, match="mode"):
        run("solo", 2)
    with pytest.raises(ValueError, match=r"\[2, 8\]"):
        run("cooperative", 1)
