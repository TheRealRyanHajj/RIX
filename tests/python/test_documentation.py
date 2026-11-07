from __future__ import annotations

import ast
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
GUIDES = ROOT / "docs" / "guides"
REQUIRED_MULTIPLAYER_GUIDES = (
    "sending-a-network-message.md",
    "hosting-a-pygame-game.md",
    "joining-a-game.md",
    "creating-a-dedicated-server.md",
    "synchronizing-objects.md",
    "making-a-multiplayer-fps.md",
    "creating-your-first-state-machine.md",
    "making-a-menu-screen.md",
    "creating-enemy-ai-states.md",
    "using-a-pause-screen.md",
    "server-side-state-machines.md",
)


def _python_fences(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    return tuple(re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL))


def test_required_multiplayer_guides_exist_are_indexed_and_parse() -> None:
    index = (GUIDES / "README.md").read_text(encoding="utf-8")
    for name in REQUIRED_MULTIPLAYER_GUIDES:
        path = GUIDES / name
        assert path.is_file()
        assert name in index
        snippets = _python_fences(path)
        assert snippets
        for number, snippet in enumerate(snippets, 1):
            ast.parse(snippet, filename=f"{path}:python-fence-{number}")


def test_feature_reference_python_fences_parse() -> None:
    path = ROOT / "features.md"
    snippets = _python_fences(path)
    assert len(snippets) >= 60
    for number, snippet in enumerate(snippets, 1):
        ast.parse(snippet, filename=f"{path}:python-fence-{number}")
