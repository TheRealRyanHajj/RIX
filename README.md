# Easy3D

Easy3D is a private, Windows-first 3D framework with a Python API and a C++20
native core. The current implementation includes the validated Phase 0 native
foundation and Phase 1.1's generation-safe scene/entity lifetime system.
Rendering remains the Phase 0 blank D3D11 window until later Phase 1 milestones
are completed.

The product and technical source of truth is [MASTERPLAN.md](MASTERPLAN.md).
Validation evidence and environment-specific limitations are recorded in
[docs/progress.md](docs/progress.md) and [docs/known-issues.md](docs/known-issues.md).

## Prerequisites

- Windows 10 or 11 x64
- Visual Studio Build Tools with **Desktop development with C++**, an x64 MSVC
  toolset, and a Windows 10/11 SDK. Visual Studio 2022/MSVC v143 is the intended
  minimum; the recorded Phase 0 run used Build Tools 2026/MSVC 19.51.
- CPython 3.11 x64 (3.12 and 3.13 are permitted but are not Phase 0 acceptance
  substitutes until independently validated)
- Git, CMake 3.26+, and Ninja 1.11+
- Network access on the first configure to fetch immutable dependency commits

No global vcpkg, SDL, or bgfx installation is required.

## Developer setup

Open a PowerShell prompt where the x64 MSVC compiler is available (for example
the **Developer PowerShell** installed with Visual Studio) and run from the
repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -c "import easy3d; print(easy3d.engine_version())"
python -m pytest -q
```

The editable install performs the CMake native build. A direct native build is
also available:

```powershell
cmake --preset windows-debug
cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
```

The presets use Ninja Multi-Config and therefore require `cl.exe` to be on
`PATH`. They do not install or alter global software.

## Interactive graphics smoke test

Run this only from an interactive Windows desktop session with a D3D11-capable
graphics driver:

```powershell
python examples/00_window/main.py
```

A resizable slate-blue window should appear. Resize it, then close it with the
window close control or Escape. The console logs the selected bgfx renderer and
PCI vendor/device IDs. This is a manual GPU test and is deliberately excluded
from `pytest` and CTest.

For a short visible open/close lifecycle diagnostic (still requiring a real
Windows desktop/GPU), run `python tests/manual/window_lifecycle.py`.

## Scene and entity lifecycle

Entities belong to an explicit scene, either through a context or a `scene=`
argument:

```python
from easy3d import Entity, Game, Scene

world = Scene("main")
with world:
    player = Entity("player")
    prop = Entity("prop")

game = Game("My Game")
game.load_scene(world)
```

Run `python examples/01_entity_lifecycle/main.py` for creation, destruction,
stale-handle rejection, unload, and cleanup. See
[docs/api-contract.md](docs/api-contract.md) for the implemented contract.

## Benchmarks

After installation, run the small native-call harness with:

```powershell
python benchmarks/native_add.py --iterations 1000000
```

It measures Python-to-native call overhead; it is infrastructure, not an engine
performance claim.

## Scope and license

Transforms/renderable entities, physics, assets, and multiplayer systems remain
incomplete. The repository is private and proprietary; dependencies retain the
licenses recorded in [LICENSES/THIRD_PARTY.md](LICENSES/THIRD_PARTY.md).

