# Easy3D implementation progress

**Current status (2026-11-01): Phase 0 and Phase 1.1–1.10 checklist items
PASSED; Phase 1 exit-gate camera motion awaits the Phase 2 scheduler.** Earlier
blocked checkpoints below are retained as diagnostic history.

## 2026-11-01 — Phase 0 kickoff

### Bounded approach

Scope is limited to `MASTERPLAN.md` Phase 0 (0.1–0.10). The implementation will:

1. inventory the clean repository and Windows toolchain;
2. bootstrap only the native core, Python binding/package, platform window/renderer, tests, example, and Phase 0 documentation;
3. pin SDL3, bgfx, pybind11, and Python build/test dependencies;
4. build and run every test supported by this machine, fixing failures rather than bypassing them;
5. leave GPU/window validation explicitly unverified unless the example is run interactively on this Windows desktop.

Expected files affected: root build/package configuration, `engine/`, `bindings/`, `python/easy3d/`, `tests/`, `examples/00_window/`, `cmake/`, `LICENSES/`, and Phase 0 documentation. No scene, entity, physics, networking, or gameplay systems will be added.

Primary risks: Visual Studio/MSVC and Python 3.11 are not currently installed; bgfx/SDL native handle and renderer lifecycle must be implemented without falsely claiming runtime proof. Planned verification commands are `python -m pip install -e '.[dev]'`, `python -m pytest -q`, CMake configure/build plus `ctest`, the import one-liner, and an explicitly interactive window example.

### 0.1 repository and environment inventory

Initial repository state:

```text
git status --short --branch
## main
?? masterplan.md

rg --files
masterplan.md
```

The sole file was the user-provided, untracked 346-line master plan. It was read in full before edits. Windows filename matching is case-insensitive, so it will be case-normalized to the required `MASTERPLAN.md` without changing content.

Commands and exact outputs:

```text
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture
Caption: Microsoft Windows 11 Home
Version: 10.0.26200
BuildNumber: 26200
OSArchitecture: 64-bit

$PSVersionTable.PSVersion
7.6.5

py -0p
 -V:3.13 *        C:\Program Files\Python313\python.exe
 -V:3.12          C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.12_3.12.2800.0_x64__qbz5n2kfra8p0\python3.12.exe

py -3.11 --version
No suitable Python runtime found

python --version
Python 3.13.2

python -c "import sys,platform; print(sys.executable); print(platform.platform()); print(platform.machine())"
C:\Program Files\Python313\python.exe
Windows-11-10.0.26200-SP0
AMD64

git --version
git version 2.45.1.windows.1

cmake --version
cmake version 4.0.1

ninja --version
1.12.1

cl
The term 'cl' is not recognized as a name of a cmdlet, function, script file, or executable program.

vswhere -all -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json
[]

vcpkg version
The term 'vcpkg' is not recognized as a name of a cmdlet, function, script file, or executable program.

conan --version
The term 'conan' is not recognized as a name of a cmdlet, function, script file, or executable program.

winget --version
v1.29.380

choco --version
The term 'choco' is not recognized as a name of a cmdlet, function, script file, or executable program.

scoop --version
The term 'scoop' is not recognized as a name of a cmdlet, function, script file, or executable program.
```

Missing required prerequisites: Visual Studio 2022 Build Tools with the Desktop development with C++ workload (MSVC and Windows SDK), and CPython 3.11 x64. CMake, Ninja, Git, Python 3.12/3.13, and Windows Package Manager are available. No dependency manager is installed; Phase 0 will use pinned CMake dependency acquisition so no global dependency-manager installation is required.

Status: **0.1 DONE** (inventory independently executed and recorded). Build/install acceptance remains blocked until the missing compiler is installed or another supported MSVC environment is made available.

## 2026-11-01 — Phase 0 implementation checkpoint

### Implemented

- C++20 `easy3d_core`, version/configuration API, strict warning flags, native
  CTest, and native benchmark target.
- scikit-build-core/pybind11 editable packaging for `easy3d._easy3d`, typed
  public Python package, registered `EngineError`, `engine_version`,
  `native_add`, and lazy native `Engine` lifecycle.
- SDL3 Win32 resizable window/event loop and monotonic frame timing.
- bgfx D3D11 initialization, clear/touch/present, resize/reset, renderer/adapter
  logging, and shutdown-before-HWND destruction.
- Python `Game`, blank-window example, visible lifecycle diagnostic, non-GPU
  Python/native tests, dependency/license pins, setup docs, and known issues.

No Phase 1+ gameplay, scene, physics, asset, or network work was started.

### Commands and exact decisive outputs

Supported MSVC preset (expected blocker on this machine):

```text
cmake --preset windows-debug
-- The CXX compiler identification is unknown
CMake Error at CMakeLists.txt:3 (project):
  The CMAKE_CXX_COMPILER:

    cl

  is not a full path and was not found in the PATH.
-- Configuring incomplete, errors occurred!
```

Graphics-disabled portable-core diagnostic:

```text
cmake -S . -B build/headless-mingw -G Ninja -DCMAKE_CXX_COMPILER=C:/mingw64/bin/g++.exe -DEASY3D_ENABLE_GRAPHICS=OFF -DEASY3D_BUILD_PYTHON=OFF -DEASY3D_BUILD_BENCHMARKS=ON -DBUILD_TESTING=ON
-- Configuring done
-- Generating done
-- Build files have been written to: C:/Users/Ryan/Desktop/code/Easy3D/build/headless-mingw

cmake --build build/headless-mingw
ninja: no work to do.

ctest --test-dir build/headless-mingw --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/headless-mingw
    Start 1: easy3d.core
1/1 Test #1: easy3d.core ......................   Passed    0.01 sec

100% tests passed, 0 tests failed out of 1
Total Test time (real) =   0.03 sec
```

Full graphics-enabled diagnostic compilation and non-GPU CTest:

```text
cmake -S . -B build/graphics-mingw -G Ninja -DCMAKE_CXX_COMPILER=C:/mingw64/bin/g++.exe -DCMAKE_C_COMPILER=C:/mingw64/bin/gcc.exe -DEASY3D_ENABLE_GRAPHICS=ON -DEASY3D_BUILD_PYTHON=OFF -DEASY3D_BUILD_BENCHMARKS=OFF -DBUILD_TESTING=ON
-- SDL3 was configured with the following options:
-- Platform: Windows-6.2.9200
-- 64-bit:   TRUE
-- Compiler: C:/mingw64/bin/gcc.exe
-- Revision: SDL-3.4.18-release-3.4.18
-- Build Shared Library: OFF
-- Build Static Library: ON
-- Configuring done
-- Generating done

cmake --build build/graphics-mingw --target easy3d_core_tests -j 4
[1/3] Building CXX object CMakeFiles/easy3d_core_tests.dir/tests/cpp/test_core.cpp.obj
[2/3] Linking CXX executable easy3d_core_tests.exe

ctest --test-dir build/graphics-mingw --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/graphics-mingw
    Start 1: easy3d.core
1/1 Test #1: easy3d.core ......................   Passed    0.07 sec

100% tests passed, 0 tests failed out of 1
Total Test time (real) =   1.01 sec
```

The first isolated Python 3.13 editable build completed but import found missing
MinGW runtime DLLs. This failure was fixed by static GCC/C++ runtime linkage and
installing the compiler-matched `libwinpthread-1.dll` only for MinGW builds:

```text
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
Successfully built easy3d
Successfully installed colorama-0.4.6 easy3d-0.1.0 iniconfig-2.3.1 packaging-26.3 pluggy-1.7.0 pygments-2.21.0 pytest-9.2.0

python -c "import easy3d; print(easy3d.engine_version())"
0.1.0

python -m pytest -q
.............                                                            [100%]
13 passed in 0.04s
```

This is Python 3.13.2 + MinGW 15.1 diagnostic evidence, not the required Python
3.11 + MSVC acceptance evidence.

Benchmark harness:

```text
python benchmarks/native_add.py --iterations 1000000
iterations=1000000 elapsed_seconds=0.097206 ns_per_call=97.2 final_value=500000
```

The number is a harness baseline on this particular Python 3.13/MinGW build,
not an engine performance guarantee.

Syntax/configuration checks:

```text
python -m compileall -q python tests examples benchmarks
# exit code 0, no output

cmake --list-presets
Available configure presets:

  "windows-debug"   - Windows x64 Debug
  "windows-release" - Windows x64 Release
```

### GPU/window failure evidence

Command:

```text
python tests/manual/window_lifecycle.py
# process exit code -1073741819 (Windows 0xC0000005 access violation)
```

The equivalent symbol-bearing native diagnostic was run under GDB. Relevant
exact output:

```text
BGFX Version 1.167.9149
BGFX NVIDIA GeForce RTX 3070 Ti
BGFX Direct3D11 device feature level 12.1.
BGFX Failed to create swap chain, hr 0x887a0001.
BGFX CreateSwapChain with DXGI_SWAP_EFFECT(4) failed with HRESULT(887a0001)

Thread 10 "bgfx - renderer backend thread" received signal SIGSEGV, Segmentation fault.
#0  dxgi!CompatString () from C:\WINDOWS\SYSTEM32\dxgi.dll
#7  bgfx::Dxgi::createSwapChain (...) at .../bgfx-src/src/dxgi.cpp:529
#8  bgfx::d3d11::RendererContextD3D11::init (...) at .../bgfx-src/src/renderer_d3d11.cpp:1215
#10 bgfx::rendererCreate (...) at .../bgfx-src/src/bgfx.cpp:3883
```

The window and D3D11 adapter discovery therefore occurred, but no clear/present,
resize, clean exit, or repeated lifecycle pass is claimed. The likely
toolchain-specific failure must first be reproduced under the locked MSVC
toolchain; see `docs/known-issues.md`.

### Phase 0 item status

| Item | Status | Evidence / blocker |
|---|---|---|
| 0.1 | **DONE** | Repository/toolchain inventory above. |
| 0.2 | **DONE** | Structure, docs, formatting, ignore and license files present; config parsers pass. |
| 0.3 | **BLOCKED/UNVERIFIED** | Core and CTest pass with GNU 15.1, but required MSVC Debug/Release builds cannot run. |
| 0.4 | **BLOCKED/UNVERIFIED** | Editable install/import passes on Python 3.13 + MinGW; Python 3.11 + MSVC is unavailable. |
| 0.5 | **DONE** | Native CTest and 13 Python tests verify version, add, exception translation and lazy Engine state. |
| 0.6 | **BLOCKED/UNVERIFIED** | SDL path compiles and creates a window, but the combined run crashes during renderer init before clean close proof. |
| 0.7 | **BLOCKED/UNVERIFIED** | D3D11 adapter is discovered; bgfx MinGW swap-chain creation fails/faults. |
| 0.8 | **BLOCKED/UNVERIFIED** | `Game` construction/tests pass; `run()` cannot complete the GPU lifecycle. |
| 0.9 | **DONE** | Non-GPU tests pass; visible commands are explicit and excluded from automated suites. |
| 0.10 | **DONE** | Harness, measured diagnostic timing, instructions, immutable pins, notices and known issues are present. |

Phase 0 exit gate: **NOT PASSED**. Precise next step: install/activate VS2022
Build Tools (MSVC v143 + Windows SDK) and CPython 3.11 x64, run the documented
MSVC commands, and reproduce the window example before changing the bgfx pin or
swap-chain implementation.

## 2026-11-01 — Phase 0 completion after prerequisite recheck

### Blocker recheck and toolchain

The missing-prerequisite blockers are resolved. Exact decisive inventory:

```text
vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools

py -0p
 -V:3.13          C:\Program Files\Python313\python.exe
 -V:3.12          C:\Users\Ryan\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\python.exe
 -V:3.11[-64] *   C:\Users\Ryan\AppData\Local\Python\pythoncore-3.11-64\python.exe

py -3.11 --version
Python 3.11.9

cmake --version
cmake version 4.0.1

ninja --version
1.12.1

VsDevCmd.bat -arch=amd64 && cl
Microsoft (R) C/C++ Optimizing Compiler Version 19.51.36260 for x64
C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\cl.exe
```

Visual Studio reports Build Tools 2026 v18.11.3. The installed Windows SDK is
10.0.26100.0. This is newer than the plan's intended VS 2022/v143 minimum; see
ADR-0004 for the exact compatibility claim.

### D3D11 crash diagnosis and correction

The MSVC build reproduced the earlier access violation, proving that it was not
a MinGW-only backend issue. A temporary descriptor trace recorded this invalid
primary swap-chain format before the failed DXGI call:

```text
BGFX Easy3D probe: hwnd=0x3108cc valid=1 size=640x360 format=155467664 ...
BGFX Failed to create swap chain, hr 0x887a0001.
Thread 1 received signal SIGSEGV ... dxgi!CompatString
```

Root cause: Easy3D assigned a separately constructed `bgfx::SwapChain` to
`bgfx::Init::swapChain`. The standalone descriptor uses `TextureFormat::Count`
sentinels, so this overwrote `bgfx::Init`'s valid primary defaults (`BGRA8`,
`D24S8`, two back buffers) and indexed beyond bgfx's format table. The fix
configures `bgfx::Init::swapChain` first, copies that complete descriptor for
later resize resets, and keeps the lifecycle on the SDL window thread. No bgfx
source patch or dependency-pin change is part of the repository.

The corrected Debug diagnostic showed `format=87` (`BGRA8`) and completed:

```text
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
frames=52 running=0
```

### Native build and test evidence

Both presets were freshly configured under the x64 developer environment and
successfully built all targets (407 build steps on the first full build):

```text
cmake --fresh --preset windows-debug
-- The CXX compiler identification is MSVC 19.51.36260.0
-- Configuring done
-- Generating done
-- Build files have been written to: C:/Users/Ryan/Desktop/code/Easy3D/build/windows-debug

cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-debug
    Start 1: easy3d.core
1/1 Test #1: easy3d.core ......................   Passed    0.07 sec
100% tests passed, 0 tests failed out of 1
Total Test time (real) =   0.11 sec

cmake --fresh --preset windows-release
-- The CXX compiler identification is MSVC 19.51.36260.0
-- Configuring done
-- Generating done
-- Build files have been written to: C:/Users/Ryan/Desktop/code/Easy3D/build/windows-release

cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-release
    Start 1: easy3d.core
1/1 Test #1: easy3d.core ......................   Passed    0.05 sec
100% tests passed, 0 tests failed out of 1
Total Test time (real) =   0.09 sec

.\build\windows-release\Release\easy3d_window_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
frames=49 running=0
```

The pinned bx/bgfx projects emit compiler-option override warnings in some
translation units under MSVC 19.51; there were no Easy3D compile errors or test
failures.

### Python 3.11 editable install and test evidence

The acceptance environment is an ignored venv at `build/venv311`:

```text
py -3.11 -m venv build/venv311
build\venv311\Scripts\python.exe -m pip install -e ".[dev]"
Building editable for easy3d (pyproject.toml): finished with status 'done'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl size=1750695 sha256=a4d7279f14ead3a577a869f5f21185f73aa601546da4f9722e2585b187aba224
Successfully built easy3d
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
0.1.0

build\venv311\Scripts\python.exe -m pytest -q
.............                                                            [100%]
13 passed in 0.04s

build\venv311\Scripts\python.exe tests\manual\window_lifecycle.py
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
iteration=1 frames=51 running=False
iteration=2 frames=57 running=False
```

Two exploratory command names were incorrect and failed without changing code:
`easy3d.native_smoke_test` does not exist (the public smoke function is
`native_add`), and `benchmarks/native_call.py` does not exist (the file is
`benchmarks/native_add.py`). The corrected commands passed:

```text
build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version()); print(easy3d.native_add(20, 22))"
0.1.0
42

build\venv311\Scripts\python.exe benchmarks\native_add.py
iterations=1000000 elapsed_seconds=0.184044 ns_per_call=184.0 final_value=500000

.\build\windows-release\Release\easy3d_core_benchmark.exe
iterations=10000000 elapsed_seconds=0.013628 final_value=5000000
```

Benchmark numbers are one-run harness evidence, not performance guarantees.

### Interactive Windows GPU evidence

`build\venv311\Scripts\python.exe examples\00_window\main.py` was run in a
GUI-capable Windows desktop session. Windows UI automation selected the unique
native window titled `Easy3D — Phase 0` and captured the slate-blue D3D11 clear.
It invoked the native Maximize control; the accessibility state changed from
`Maximize` to `Restore`, the client expanded to the 1920x1080 desktop, and the
entire resized client remained correctly cleared. It then invoked the native
Close control. A fresh window inventory contained no matching window and the
Python process exited with code 0.

Validated hardware/renderer log:

```text
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
```

This proves the D3D11 path on the NVIDIA GeForce RTX 3070 Ti used for this run;
it does not make claims for other adapters or backends.

Final source/checklist consistency commands:

```text
build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output

build\venv311\Scripts\python.exe -m pytest -q
.............                                                            [100%]
13 passed in 0.04s

clang-format --version
The term 'clang-format' is not recognized as a name of a cmdlet, function,
script file, or executable program.
```

The optional formatter executable is unavailable, so no automated format check
is claimed. The repository does contain `.clang-format`, and the changed C++
source was compiled successfully with the strict Easy3D warning settings in
both MSVC configurations.

### Final Phase 0 status

| Item | Status | Completion evidence |
|---|---|---|
| 0.1 | **DONE** | Repository and refreshed toolchain inventory recorded. |
| 0.2 | **DONE** | Minimal structure, docs, formatting, ignore and license/notice files present. |
| 0.3 | **DONE** | MSVC Debug/Release builds and both CTest runs pass. |
| 0.4 | **DONE** | CPython 3.11 editable wheel builds, installs and imports. |
| 0.5 | **DONE** | Native and 13 Python tests cover version, add and exception translation. |
| 0.6 | **DONE** | SDL window opens, polls, resizes and cleanly closes on the real desktop. |
| 0.7 | **DONE** | Pinned bgfx D3D11 clear/present, resize/reset and clean shutdown verified. |
| 0.8 | **DONE** | Python `Game` example and two repeated open/close iterations pass. |
| 0.9 | **DONE** | Automated non-GPU tests remain separate from explicit visible diagnostics. |
| 0.10 | **DONE** | Benchmarks, setup, immutable pins, notices and limitations recorded. |

Phase 0 exit gate: **PASSED**. Work stopped at the original delivery checkpoint
with no Phase 1 code at that time. The later full-engine objective below
superseded that stop condition and authorized continuation at Phase 1.1.

## 2026-11-01 — Phase 1.1 scene and entity lifetime

### Implemented

- Native C++ `World` registry with O(1) free-slot reuse and native `Scene`
  ownership.
- World-scoped `EntityHandle` values containing a nonzero runtime world ID,
  slot index, and generation. Destroy and clear advance generations before
  reuse; invalid and cross-world access throws `InvalidEntityError`.
- Native entity name, enabled, and visible state plus live enumeration/counting.
- Typed public Python `Scene` and `Entity` wrappers, explicit/context-managed
  construction, permanent close vs reusable clear, and `ReferenceError`-based
  stale-handle behavior.
- `Game.load_scene`/`unload_scene`, activation, scene switching, and exclusive
  ownership between games.
- Architecture/API documentation and a runnable entity-lifecycle example.

Transform, hierarchy, component attachment, and rendering submission are not
claimed by this milestone; they remain subsequent Phase 1 items.

### Verification evidence

Debug native build and tests:

```text
cmake --build --preset windows-debug
# exit code 0; easy3d_core, easy3d_scene_tests and existing targets linked

ctest --preset windows-debug --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-debug
    Start 1: easy3d.core
1/2 Test #1: easy3d.core ......................   Passed    0.05 sec
    Start 2: easy3d.scene
2/2 Test #2: easy3d.scene .....................   Passed    0.03 sec
100% tests passed, 0 tests failed out of 2
Total Test time (real) =   0.17 sec
```

Python 3.11 editable rebuild and tests:

```text
build\venv311\Scripts\python.exe -m pip install -e ".[dev]"
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl size=1764859 sha256=5279d7016e731a6e668530372f98a18ce5d31407155bdfdffcfd086795aa953e
Successfully built easy3d
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
.....................                                                    [100%]
21 passed in 0.09s
```

Release build, native tests, and Phase 0 GPU regression:

```text
cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-release
    Start 1: easy3d.core
1/2 Test #1: easy3d.core ......................   Passed    0.04 sec
    Start 2: easy3d.scene
2/2 Test #2: easy3d.scene .....................   Passed    0.04 sec
100% tests passed, 0 tests failed out of 2
Total Test time (real) =   0.16 sec

.\build\windows-release\Release\easy3d_window_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
frames=52 running=0
```

Runnable public API example and syntax validation:

```text
build\venv311\Scripts\python.exe examples\01_entity_lifecycle\main.py
loaded 'lifecycle example' with 2 entities
destroyed id=4294967297; replacement id=8589934593
stale access rejected: invalid entity handle (world=1, index=1, generation=1); expected live entity in world 1
scene closed=True; player alive=False

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output
```

### Status and next task

Phase 1.1: **DONE**. The evidence covers native create/destroy/reuse,
cross-world rejection, Python stale-reference translation, explicit ownership,
nested contexts, scene cleanup, Debug/Release builds, and the existing D3D11
lifecycle regression.

Immediate next task: Phase 1.2 — native `Vec2`/`Vec3`/`Quat`, public Euler
facade, transform storage, parenting with cycle rejection and keep-world
semantics, dirty propagation, and local/world correctness tests.

## 2026-11-01 — Phase 1.2 math and transform hierarchy

### Implemented

- Immutable-pinned GLM 1.0.1 as a private implementation dependency.
- Native Easy3D `Vec2`, `Vec3`, `Quat`, and `Transform` values with arithmetic,
  normalization, dot/cross operations, quaternion multiplication/rotation,
  approximate comparison, and degree-based Euler conversion.
- Native local TRS storage, quaternion normalization, cached world matrices,
  recursive dirty propagation, parent/child links, cycle/self/cross-world
  rejection, keep-local and keep-world reparenting, and world-preserving child
  detachment when a parent is destroyed.
- Typed Python `Vec2`, `Vec3`, and `Quat` APIs. Entity `position`, `rotation`, and
  `scale` are live proxies, so component mutation writes through to native state.
  World transform snapshots, `parent`, `children`, and explicit `set_parent`
  are public.
- Right-handed, +Y-up, -Z-forward and Euler/quaternion semantics documented.

### Failure and correction evidence

The first Debug compile stopped before linking because pinned GLM requires an
explicit opt-in for its matrix decomposition extension:

```text
glm/gtx/matrix_decompose.hpp(24): fatal error C1189:
"GLM: GLM_GTX_matrix_decompose is an experimental extension ...
Use #define GLM_ENABLE_EXPERIMENTAL before including it"
ninja: build stopped: subcommand failed.
```

`GLM_ENABLE_EXPERIMENTAL` is now scoped to `scene.cpp`, the only translation
unit using that pinned extension. The rebuild passed.

The first Python run then exposed a non-unique Euler representation after
incrementing yaw from 90° to 135°:

```text
entity.rotation
Vec3(180.0, 45.000003814697266, 180.0)
```

That triple is orientation-equivalent to `(0, 135, 0)` and the native quaternion
was correct. The regression now compares quaternion orientation, and the public
contract explicitly states that Euler triples may canonicalize.

### Verification evidence

```text
cmake --build --preset windows-debug
# exit code 0

ctest --preset windows-debug --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-debug
    Start 1: easy3d.core
1/3 Test #1: easy3d.core ......................   Passed    0.05 sec
    Start 2: easy3d.scene
2/3 Test #2: easy3d.scene .....................   Passed    0.03 sec
    Start 3: easy3d.math_transform
3/3 Test #3: easy3d.math_transform ............   Passed    0.04 sec
100% tests passed, 0 tests failed out of 3
Total Test time (real) =   0.23 sec

build\venv311\Scripts\python.exe -m pip install -e ".[dev]"
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl size=1780041 sha256=13469a18882f8b194165b862593805dbdb64604ba9d2d72c879e6bd97df33589
Successfully built easy3d
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
............................                                             [100%]
28 passed in 0.08s

cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
Test project C:/Users/Ryan/Desktop/code/Easy3D/build/windows-release
    Start 1: easy3d.core
1/3 Test #1: easy3d.core ......................   Passed    0.04 sec
    Start 2: easy3d.scene
2/3 Test #2: easy3d.scene .....................   Passed    0.04 sec
    Start 3: easy3d.math_transform
3/3 Test #3: easy3d.math_transform ............   Passed    0.03 sec
100% tests passed, 0 tests failed out of 3
Total Test time (real) =   0.22 sec

.\build\windows-release\Release\easy3d_window_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
frames=52 running=0

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output
```

Tests cover vector/quaternion behavior, exact versus approximate equality,
Euler orientation round-trip, live native property writes, local/global TRS,
rotation and scale inheritance, cache invalidation after an ancestor mutation,
cycle/self/cross-scene rejection, keep-world reparenting, and parent destruction.

Phase 1.2: **DONE**. Immediate next task: Phase 1.3 — renderer abstraction,
mesh/material handles, GPU resource lifetime, shaders, and indexed triangle/cube/
plane/sphere rendering with depth testing.

## 2026-11-01 — Phase 1.3 indexed geometry and GPU resource lifetime

### Implemented

- Backend-neutral `Color`, `Vertex`, `Bounds`, `MeshData`, and `Material`
  abstractions with finite/range/index validation and bounds/triangle queries.
- Counter-clockwise triangle, 24-vertex cube, +Y horizontal plane, and
  configurable UV-sphere generators with positions, normals, UVs, and colors.
- Private bgfx renderer extracted from the Win32 event loop. Its move-only GPU
  mesh resources own immutable vertex and 32-bit index buffers; all buffers,
  program, and uniform handles release before bgfx/device shutdown.
- Easy3D-owned solid-color vertex/fragment shaders, material color uniform,
  depth writes, `LESS` depth testing, and back-face culling.
- Reviewed D3D11 SM5 DXBC headers plus explicit pinned-shaderc regeneration via
  `EASY3D_REGENERATE_SHADERS=ON`; ordinary builds do not compile shader tools.
- An opt-in native geometry diagnostic that leaves the ordinary Python window
  blank and avoids claiming the Phase 1.4 public camera or Phase 1.7 components.

### Failure and correction evidence

The first shader-tool configure inherited an unset include variable and invoked
both Debug compiler processes with `-i /src`; both produced zero-byte headers
and stalled. The build was interrupted without accepting those outputs.
Resolving the nested FetchContent `bgfx` source directory produced valid SM5
headers. The full tool build also demonstrated that enabling shaderc adds 713
first-build Ninja steps on this revision, so ADR-0007 records the reviewed,
committed-artifact approach and opt-in regeneration path.

### Verification evidence

Debug and Release native suites:

```text
cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
1/4 easy3d.core             Passed
2/4 easy3d.scene            Passed
3/4 easy3d.math_transform   Passed
4/4 easy3d.mesh             Passed
100% tests passed, 0 tests failed out of 4
Total Test time (real) = 0.28 sec

cmake --preset windows-release
cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
1/4 easy3d.core             Passed
2/4 easy3d.scene            Passed
3/4 easy3d.math_transform   Passed
4/4 easy3d.mesh             Passed
100% tests passed, 0 tests failed out of 4
Total Test time (real) = 0.28 sec
```

Release GPU diagnostic on the interactive Windows desktop:

```text
.\build\windows-release\Release\easy3d_geometry_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
Easy3D geometry: GPU meshes=4, indexed triangles=783, depth-test=less
easy3d_geometry_lifecycle: PASS frames=1032
EXIT_CODE=0
```

A live Windows.Graphics.Capture screenshot was inspected while the Debug
diagnostic was rendering. It visibly showed the colored triangle, cyan cube,
yellow sphere, and gray floor plane; foreground geometry correctly occluded the
plane. This is genuine interactive evidence on the NVIDIA GeForce RTX 3070 Ti,
not an inference from process exit.

Python 3.11 packaging regression:

```text
build\venv311\Scripts\python.exe -m pip install -e ".[dev]"
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=3209650
sha256=ca09e59f61b10c050928f8b61bc2087e1f0f4b4cd19867449efdbf851a666c75
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
0.1.0

build\venv311\Scripts\python.exe -m pytest -q
............................                                             [100%]
28 passed in 0.07s

build\venv311\Scripts\python.exe -m compileall -q python examples
# exit code 0, no output
```

The native mesh tests cover primitive counts, bounds, front-face winding,
sphere radii and unit normals, invalid indices/sizes, and RGBA8 packing. The GPU
diagnostic remains intentionally excluded from CTest because it opens a visible
window and requires a real D3D11 desktop.

Phase 1.3: **DONE**. Immediate next task: Phase 1.4 — scene-facing camera data,
configurable near/far projection, aspect ratio, and resize behavior tests.

## 2026-11-01 — Phase 1.4 camera, projection, and resize

### Implemented

- Easy3D-owned column-major `Matrix4` and perspective `Camera` native values.
- Position/quaternion orientation, -Z forward/+Y up/+X right basis, validated
  vertical FOV, configurable positive near/far planes, and robust `look_at`.
- Backend-capability projection for D3D `[0,1]` and homogeneous `[-1,1]` depth.
- Renderer diagnostic migrated from hard-coded GLM matrices to the native
  camera. Projection aspect is recomputed from current SDL pixel dimensions
  after swap-chain/view resize.
- Typed public Python `Camera` with mutable `Vec3` position/Euler rotation,
  basis vectors, `look_at`, aspect queries, and view/projection matrix tuples.
  Scene attachment is explicitly deferred rather than simulated.

### Verification evidence

```text
cmake --build --preset windows-debug
ctest --preset windows-debug --output-on-failure
1/5 easy3d.core             Passed
2/5 easy3d.scene            Passed
3/5 easy3d.math_transform   Passed
4/5 easy3d.mesh             Passed
5/5 easy3d.camera           Passed
100% tests passed, 0 tests failed out of 5
Total Test time (real) = 0.49 sec

build\venv311\Scripts\python.exe -m pip install -e ".[dev]"
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=3216116
sha256=fa9d07defc6883d76a70584cec4919d08372b185acf1935bc3220e858d38b0ea
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
....................................                                     [100%]
36 passed in 0.42s

cmake --build --preset windows-release
ctest --preset windows-release --output-on-failure
1/5 easy3d.core             Passed
2/5 easy3d.scene            Passed
3/5 easy3d.math_transform   Passed
4/5 easy3d.mesh             Passed
5/5 easy3d.camera           Passed
100% tests passed, 0 tests failed out of 5
Total Test time (real) = 0.36 sec

.\build\windows-release\Release\easy3d_geometry_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
Easy3D geometry: GPU meshes=4, indexed triangles=783, depth-test=less
easy3d_geometry_lifecycle: PASS frames=1033
EXIT_CODE=0
```

Native camera tests verify look-at basis and view-space mapping, FOV/aspect
projection terms, resize invariants, exact near/far depth mapping for both clip
conventions, and invalid clipping/viewport/look-at rejection. Python tests
verify the public facade and validation.

A live Windows capture then resized the running D3D11 diagnostic from 962×572
to 701×572 through the native window border. Rendering continued, the refreshed
capture preserved cube and sphere proportions, and the plane/framing adapted to
the narrower aspect. This directly exercises SDL pixel-size handling, bgfx reset
and view-rect update, and per-frame camera projection recomputation.

Phase 1.4: **DONE**. Immediate next task: Phase 1.5 — shared PNG/JPEG texture
decode/upload/cache, sampler and sRGB semantics, UV shader path, and missing
asset errors.

## 2026-11-01 — Phase 1.5 texture assets and sampling

### Implemented

- Engine-owned RGBA8 `ImageData`, explicit linear/sRGB intent, filter/wrap
  sampler values, actionable asset exceptions, and pinned bimg PNG/JPEG decode.
- Thread-safe shared CPU cache keyed by canonical path plus color space, with
  Windows case folding and reference-safe clearing.
- Private move-only bgfx texture handles, capability validation, sampler/sRGB
  flag mapping, deterministic pre-shutdown release, and texture byte counts.
- D3D11 textured shader variant using mesh UVs and a visible nearest-filtered
  sRGB checker diagnostic. Reviewed DXBC headers were regenerated with pinned
  shaderc 1.19.167.
- Typed `easy3d.assets` Python facade, PNG/JPEG and error tests, API contract,
  dependency notices, and ADR-0009.

The initial remembered 1×1 PNG fixture was accepted by Windows imaging but
rejected by strict LodePNG CRC/stream validation. It was replaced with a fresh
valid 2×2 RGBA PNG; no decoder check was bypassed.

### Exact verification evidence

```text
cmake --build --preset windows-debug -j 8
[11/12] Linking CXX executable Debug\easy3d_geometry_lifecycle.exe

ctest --preset windows-debug --output-on-failure
1/6 Test #1: easy3d.core ......................   Passed    0.05 sec
2/6 Test #2: easy3d.scene .....................   Passed    0.04 sec
3/6 Test #3: easy3d.math_transform ............   Passed    0.03 sec
4/6 Test #4: easy3d.mesh ......................   Passed    0.04 sec
5/6 Test #5: easy3d.camera ....................   Passed    0.04 sec
6/6 Test #6: easy3d.texture ...................   Passed    0.05 sec
100% tests passed, 0 tests failed out of 6
Total Test time (real) =   0.53 sec

cmake --build --preset windows-release -j 8
[19/20] Linking CXX executable Release\easy3d_geometry_lifecycle.exe

ctest --preset windows-release --output-on-failure
1/6 Test #1: easy3d.core ......................   Passed    0.04 sec
2/6 Test #2: easy3d.scene .....................   Passed    0.04 sec
3/6 Test #3: easy3d.math_transform ............   Passed    0.03 sec
4/6 Test #4: easy3d.mesh ......................   Passed    0.03 sec
5/6 Test #5: easy3d.camera ....................   Passed    0.03 sec
6/6 Test #6: easy3d.texture ...................   Passed    0.05 sec
100% tests passed, 0 tests failed out of 6
Total Test time (real) =   0.39 sec

build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=4259459
sha256=55e2b364654d5a37550c9e207c58bc049f874b67285232c2a0220ad16312b03b
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
......................................                                   [100%]
38 passed in 0.50s

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
0.1.0

build\windows-release\Release\easy3d_geometry_lifecycle.exe
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
Easy3D geometry: GPU meshes=4, indexed triangles=783, GPU textures=1, texture bytes=256, depth-test=less, sRGB=enabled
easy3d_geometry_lifecycle: PASS frames=1032
EXIT_CODE=0
```

Interactive computer-use inspection on the Windows 11 desktop raised the
native SDL window above its console and visibly confirmed the full 8×8
blue/white checker plus red/green/yellow/magenta `(0,0)`/`(1,0)`/`(0,1)`/`(1,1)`
corner markers mapped across the plane, three solid meshes correctly
depth-tested above it, and the expected D3D11 clear. This is genuine visual
evidence on the NVIDIA GeForce RTX 3070 Ti; no other GPU backend is claimed.

Phase 1.5: **DONE**. Immediate next task: Phase 1.6 — `.obj` loading with
normals, UVs, material/texture assignment where practical, explicit limits,
malformed/missing model errors, and shared mesh resources.

Additional graphics-disabled compatibility check:

```text
cmake -S . -B build/windows-headless -G Ninja -DCMAKE_BUILD_TYPE=Release -DEASY3D_ENABLE_GRAPHICS=OFF -DEASY3D_BUILD_PYTHON=OFF -DEASY3D_BUILD_BENCHMARKS=OFF -DBUILD_TESTING=ON
cmake --build build/windows-headless -j 8
ctest --test-dir build/windows-headless --output-on-failure
100% tests passed, 0 tests failed out of 5
Total Test time (real) =   0.38 sec
```

The headless build keeps asset types but intentionally excludes image decoding;
client texture support is unaffected. This is recorded in known issues rather
than being hidden as an unsupported-server dependency.

## 2026-11-01 — Phase 1.6 OBJ/MTL model assets

### Implemented

- Immutable-pinned tinyobjloader `v2.0.0rc13`, linked privately and converted
  completely into Easy3D-owned model/material/mesh values.
- Canonical, case-folded-on-Windows, mutex-protected `ModelCache` sharing parsed
  model and mesh arrays across references and future instances.
- Polygon triangulation, shape/material part splitting, 32-bit indices,
  positions, normalized source normals, optional vertex RGB and UVs.
- Flat per-triangle normals for incomplete source normals, degenerate rejection,
  and OBJ-to-Easy3D V-coordinate conversion.
- MTL diffuse color/alpha and `map_Kd` path assignment, with explicit failures
  for missing MTLs, unknown materials and missing textures.
- Typed `ModelInfo`, `ModelPartInfo`, `ModelMaterialInfo`, `load_obj`, and
  `ModelCache` Python APIs plus explicit advanced-MTL/smoothing limitations.

### Exact verification evidence

```text
ctest --preset windows-debug --output-on-failure
1/7 Test #1: easy3d.core ......................   Passed    0.04 sec
2/7 Test #2: easy3d.scene .....................   Passed    0.03 sec
3/7 Test #3: easy3d.math_transform ............   Passed    0.03 sec
4/7 Test #4: easy3d.mesh ......................   Passed    0.03 sec
5/7 Test #5: easy3d.camera ....................   Passed    0.03 sec
6/7 Test #6: easy3d.model .....................   Passed    0.05 sec
7/7 Test #7: easy3d.texture ...................   Passed    0.04 sec
100% tests passed, 0 tests failed out of 7
Total Test time (real) =   0.46 sec

ctest --preset windows-release --output-on-failure
1/7 Test #1: easy3d.core ......................   Passed    0.04 sec
2/7 Test #2: easy3d.scene .....................   Passed    0.05 sec
3/7 Test #3: easy3d.math_transform ............   Passed    0.03 sec
4/7 Test #4: easy3d.mesh ......................   Passed    0.03 sec
5/7 Test #5: easy3d.camera ....................   Passed    0.03 sec
6/7 Test #6: easy3d.model .....................   Passed    0.06 sec
7/7 Test #7: easy3d.texture ...................   Passed    0.04 sec
100% tests passed, 0 tests failed out of 7
Total Test time (real) =   0.50 sec

build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=4421319
sha256=6e4959331fdaa79220cccc9eace60d13f0470edbd31d9e28a918fc9aa2ea7f13
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
........................................                                 [100%]
40 passed in 0.44s

ctest --test-dir build/windows-headless --output-on-failure
1/6 Test #1: easy3d.core ......................   Passed    0.03 sec
2/6 Test #2: easy3d.scene .....................   Passed    0.04 sec
3/6 Test #3: easy3d.math_transform ............   Passed    0.04 sec
4/6 Test #4: easy3d.mesh ......................   Passed    0.03 sec
5/6 Test #5: easy3d.camera ....................   Passed    0.03 sec
6/6 Test #6: easy3d.model .....................   Passed    0.05 sec
100% tests passed, 0 tests failed out of 6
Total Test time (real) =   0.41 sec
```

Phase 1.6: **DONE**. Immediate next task: Phase 1.7 — render components and
beginner-facing `Cube`, `Plane`, `Sphere`, and `Model` entities that reference
the shared mesh/model/texture assets without per-frame Python submission.

## 2026-11-01 — Phase 1.7 render-component continuation

### Bounded approach

The prior session left the Phase 1.7 implementation uncommitted after its live
visual-inspection step was interrupted. Before accepting the milestone, this
continuation will audit the native/Python ownership boundary and GPU cache keys,
rerun MSVC Debug and Release plus graphics-disabled native suites, rebuild the
Python 3.11 editable install, run pytest and syntax checks, and repeat the
visible D3D11 scene inspection on the Windows desktop. It will then update the
public API/architecture documentation, checklist, known limitations, and commit
only if all evidence is green. Primary risks are a dangling native scene
pointer, cross-thread mutation while `Game.run()` has released the GIL, and
incorrect GPU resource sharing across sampler variants.

### Implemented

- Native singleton `RenderComponent` storage in generation-checked world slots,
  including deterministic teardown on remove, destroy, clear, and slot reuse.
- Process-shared immutable cube/plane/sphere meshes and per-world canonical
  texture/model caches; model parts retain parsed OBJ/MTL resources.
- Native renderer traversal of the loaded active scene, visibility/enabled
  filtering, world-transform submission, primitive and model-part drawing, MTL
  diffuse color/texture application, and GPU mesh/texture sharing.
- GPU texture cache identity includes image plus sampler settings; an audit
  corrected the initial image-only key before acceptance.
- Typed Python `Cube`, `Plane`, `Sphere`, `Model`, and live `MeshRenderer` APIs,
  generic component lookup/removal, transactional constructor rollback, and
  `Game` scene-to-native-renderer wiring.
- Public scene/entity/component mutation is rejected while `Game.run()` is
  traversing the native registry. Runtime updates remain a Phase 2 scheduler
  responsibility rather than an unsafe cross-thread mutation path.

### Exact verification evidence

Final MSVC Debug suite:

```text
cmake --build --preset windows-debug -j 8
ctest --preset windows-debug --output-on-failure
1/8 easy3d.core                Passed
2/8 easy3d.scene               Passed
3/8 easy3d.math_transform      Passed
4/8 easy3d.mesh                Passed
5/8 easy3d.camera              Passed
6/8 easy3d.model               Passed
7/8 easy3d.render_components   Passed
8/8 easy3d.texture             Passed
100% tests passed, 0 tests failed out of 8
Total Test time (real) = 0.91 sec
```

Final MSVC Release and graphics-disabled suites:

```text
cmake --build --preset windows-release -j 8
ctest --preset windows-release --output-on-failure
100% tests passed, 0 tests failed out of 8
Total Test time (real) = 0.52 sec

cmake --build build\windows-headless -j 8
ctest --test-dir build\windows-headless --output-on-failure
100% tests passed, 0 tests failed out of 7
Total Test time (real) = 0.48 sec
```

Python 3.11 editable packaging and tests:

```text
build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=4443597
sha256=87f2223f40a41177705cf5878b0c80cd061d270fb914b81b1583fd0a9cf42c98
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
............................................                             [100%]
44 passed in 0.52s

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
0.1.0
```

Visible Windows D3D11 diagnostic:

```text
build\venv311\Scripts\python.exe tests\manual\render_components.py --seconds 30
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
render_components: PASS frames=48504
# exit code 0; stderr empty
```

Computer-use capture on the GUI-capable Windows 11 desktop visibly confirmed a
gray plane, two independently transformed/colorized shared cube instances, a
yellow sphere, and a green generated OBJ pyramid in the same depth-tested scene.
The native Close control ended the process cleanly. This is hardware evidence on
the NVIDIA GeForce RTX 3070 Ti and does not claim another adapter or backend.

Phase 1.7: **DONE**. Immediate next task: Phase 1.8 — directional and ambient
lighting, a scene camera/light component boundary, basic lit materials, and a
debug-rendering baseline.

## 2026-11-01 — Phase 1.8 lighting and debug rendering

### Bounded approach

Add a scene-owned camera value, native ambient/directional light components,
lit/unlit material selection, normal-aware solid and textured D3D11 shaders,
and persistent scene debug lines submitted from transient GPU buffers. Expose a
typed Python `Light` entity, `LightComponent`, `Scene.camera`, and
`easy3d.debug` helpers without introducing per-frame Python rendering calls.
Validate light/component lifetime, camera assignment, material mutation, and
debug-line storage in C++/pytest; regenerate reviewed DXBC with the pinned bgfx
shader compiler; then run the full build matrix and a visible hardware
diagnostic. Primary risks are non-uniform-scale normal transforms, shader/uniform
ABI mismatch, and preserving current scene defaults when no explicit light is
created.

### Implemented

- Native singleton ambient/directional `LightComponent` storage with validated
  color/intensity, generation-safe teardown, enabled filtering, ambient
  accumulation, and first-directional selection.
- Scene-owned perspective `Camera`; projection still derives its aspect and
  depth convention from the live bgfx viewport/capabilities after resize.
- Lit/unlit material selection for primitive/model entities. Both solid and
  textured shaders use inverse-transpose world normal transforms and Lambert
  directional plus ambient illumination; scenes without explicit lights retain
  a usable default rig.
- Persistent scene debug lines with depth-tested and overlay groups, uploaded
  through frame-local bgfx transient vertex buffers and rendered unlit.
- Typed Python `Light`, live `LightComponent`, `Scene.camera`, `MeshRenderer.lit`,
  primitive `lit=`, and `easy3d.debug.line`/`axes` APIs with runtime mutation
  guards consistent with native scene traversal.
- A public-API-only manual diagnostic contrasting lit and unlit materials while
  exercising a custom camera and four debug lines.

### Exact verification evidence

Pinned Shader Model 5 compiler (all four vertex/fragment sources, `--Werror`):

```text
build\windows-debug\_deps\bgfx_cmake-build\cmake\bgfx\Debug\shaderc.exe ...
vs_solid_color.sc.bin.h   7411 bytes
vs_textured.sc.bin.h      8111 bytes
fs_solid_color.sc.bin.h   8122 bytes
fs_textured.sc.bin.h      9396 bytes
# exit code 0 for all four invocations
```

MSVC Debug, Release, and graphics-disabled suites:

```text
cmake --build --preset windows-debug -j 8
ctest --preset windows-debug --output-on-failure
100% tests passed, 0 tests failed out of 9
Total Test time (real) = 1.12 sec

cmake --build --preset windows-release -j 8
ctest --preset windows-release --output-on-failure
100% tests passed, 0 tests failed out of 9
Total Test time (real) = 0.58 sec

cmake --build build\windows-headless -j 8
ctest --test-dir build\windows-headless --output-on-failure
100% tests passed, 0 tests failed out of 8
Total Test time (real) = 0.61 sec
```

Python 3.11 editable packaging and tests:

```text
build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=2740343
sha256=eb3e7bd917b9dd1cae6d5c78e12b8a41fae4fd337bb06dea9f5665948e97096d
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
..............................................                           [100%]
46 passed in 0.24s

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
0.1.0
```

Visible Windows D3D11 diagnostic:

```text
build\venv311\Scripts\python.exe tests\manual\lighting_debug.py --seconds 2
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
lighting_debug: PASS frames=10537 debug_lines=4
# exit code 0

python tests\manual\lighting_debug.py --seconds 60
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
lighting_debug: PASS frames=105470 debug_lines=4
# exit code 0
```

Computer-use capture on the GUI-capable Windows 11 desktop visibly confirmed
directional shading across a rotated red cube and cyan sphere, a uniformly unlit
green comparison cube, the custom scene-camera framing, a shaded plane, RGB
axes, and a yellow overlay line. The native Close control ended the process
cleanly. This is hardware evidence on the NVIDIA GeForce RTX 3070 Ti/D3D11 only.

Phase 1.8: **DONE**. Immediate next task: Phase 1.9 — frustum culling,
instancing/batching, renderer counters, and benchmark scenes.

## 2026-11-01 — Phase 1.9 culling, instancing, and counters

### Bounded approach

Add native frustum extraction for both bgfx depth conventions, conservative
transformed-mesh bounds, compatibility-keyed D3D11 instancing, coherent frame
counters, and repeatable public-API diagnostics. Preserve exact non-uniform-scale
normal handling by falling back to individual draws. Validate mathematical edge
cases in graphics-independent C++ tests and require live D3D11 diagnostics to
account for every renderable as visible or culled and to prove instanced draw
submission through counters.

### Implemented

- Normalized six-plane frusta from projection × view for D3D `[0,1]` and
  homogeneous `[-1,1]` depth, plus conservative transformed bounds tests.
- Per-mesh local AABB caching and culling before texture upload or draw
  submission.
- Compatibility grouping by GPU mesh, complete material, and texture/sampler;
  matching uniform-scale groups use transient model-matrix instance buffers and
  dedicated solid/textured instanced vertex programs.
- Exact single-draw fallback for non-uniform scale or transient-buffer pressure.
- Coherent latest-frame `RendererStats` published from native atomics and exposed
  as a frozen Python value on `Game`.
- `benchmarks/render_cubes.py` with instance accounting, wall-clock FPS,
  sampled median/p95/p99 frame time, and Windows working/private-set memory.
- A five-cube live diagnostic that requires two visible cubes, three culled
  cubes, and one instanced draw.

### Exact verification evidence

```text
cmake --build --preset windows-debug -j 8
ctest --preset windows-debug --output-on-failure
100% tests passed, 0 tests failed out of 10
Total Test time (real) = 3.00 sec

cmake --build --preset windows-release -j 8
ctest --preset windows-release --output-on-failure
100% tests passed, 0 tests failed out of 10
Total Test time (real) = 0.63 sec

cmake --build build\windows-headless -j 8
ctest --test-dir build\windows-headless --output-on-failure
100% tests passed, 0 tests failed out of 9
Total Test time (real) = 0.61 sec
```

Python 3.11 editable package and public API:

```text
build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=2747035
sha256=f2644d41f678362ec98ad7fbaeacdd217511a6d0873ca41767d2686c867b722b
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
..............................................                           [100%]
46 passed in 0.23s

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output

build\venv311\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version(), easy3d.RendererStats())"
0.1.0 RendererStats(draw_calls=0, visible_instances=0, culled_instances=0, instanced_draw_calls=0)
```

Short D3D11 benchmark validation on the RTX 3070 Ti:

```text
build\venv311\Scripts\python.exe benchmarks\render_cubes.py --count 200 --seconds 2
requested_instances=200
frames=8470
overall_fps=4154.22
frame_ms_median=0.16135
frame_ms_p95=0.5571
frame_ms_p99=2.4534
renderer: draw_calls=1, visible_instances=200, culled_instances=0,
          instanced_draw_calls=1
# exit code 0
```

Targeted live culling/instancing diagnostic:

```text
build\venv311\Scripts\python.exe tests\manual\renderer_optimization.py --seconds 60
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
renderer_optimization: PASS frames=354589
RendererStats(draw_calls=1, visible_instances=2, culled_instances=3,
              instanced_draw_calls=1)
# exit code 0
```

The D3D11 programs compiled, linked, ran for 60 seconds, and returned internally
consistent live counters. The attempted dedicated computer-use image inspection
was interrupted with Escape, so the instanced image itself remains explicitly
**UNVERIFIED** rather than being overstated. Prior Phase 1.8 D3D11 output remains
visually verified; this does not block the counter/culling acceptance evidence.

Phase 1.9: **DONE**. Immediate next task: Phase 1.10 — first-world example and
the recorded 10,000-static-cube acceptance workload.

## 2026-11-01 — Phase 1.10 first-world and 10,000-cube acceptance

### Implemented

- Added native perspective/orthographic projection selection with a fixed
  positive orthographic height, D3D and homogeneous depth conventions, current
  pixel-aspect resize behavior, frustum integration, Python typing, scene
  copy-in/copy-out, and native/Python tests.
- Added `examples/02_first_world/main.py` and its run guide. The example uses
  only public API to create transformed primitives, native ambient/directional
  lights, debug axes, a decoded PNG texture, and a textured OBJ/MTL model. On
  exit it unloads with `clear=True`, verifies zero entities, and closes the
  scene.
- Added a 100-cycle scene load/unload/clear/close Python regression that checks
  stale-handle invalidation after every cycle.
- Checked Phase 1.10 after the first-world D3D11 run and full 10,000-instance
  benchmark. The separate Phase 1 exit-gate requirement for a moving camera is
  not claimed yet: runtime mutation remains intentionally guarded until Phase
  2.2 provides safe simulation boundaries.

### Validated machine

```text
OS: Microsoft Windows 11 Home 10.0.26200 (build 26200)
CPU: AMD Ryzen 5 5600G with Radeon Graphics (12 logical processors)
RAM: 34,227,388,416 bytes
GPU: NVIDIA GeForce RTX 3070 Ti
GPU driver: 32.0.16.1088
Renderer: Direct3D 11, vendor=0x10de, device=0x2482
```

`Win32_VideoController.AdapterRAM` returned a truncated value on this machine,
so GPU memory capacity is deliberately omitted rather than misreported.

### Exact verification evidence

Native Debug:

```text
cmake --build --preset windows-debug --parallel
ctest --preset windows-debug --output-on-failure
100% tests passed, 0 tests failed out of 10
Total Test time (real) = 1.08 sec
```

Native Release:

```text
cmake --build --preset windows-release --parallel
ctest --preset windows-release --output-on-failure
100% tests passed, 0 tests failed out of 10
Total Test time (real) = 0.68 sec
```

Graphics-disabled/headless:

```text
cmake --build build\windows-headless --parallel
ctest --test-dir build\windows-headless --output-on-failure
100% tests passed, 0 tests failed out of 9
Total Test time (real) = 0.55 sec
```

Python 3.11 editable build and tests:

```text
build\venv311\Scripts\python.exe -m pip install -e '.[dev]'
Created wheel for easy3d: filename=easy3d-0.1.0-cp311-cp311-win_amd64.whl
size=4463369
sha256=6047467a49d73d8962749a44ee9c3c1fd3a2c1c2efd209b465d00cd9b08212b9
Successfully installed easy3d-0.1.0

build\venv311\Scripts\python.exe -m pytest -q
.................................................                        [100%]
49 passed in 0.17s

build\venv311\Scripts\python.exe -m compileall -q python tests examples benchmarks
# exit code 0, no output
```

Timed first-world D3D11 run:

```text
build\venv311\Scripts\python.exe examples\02_first_world\main.py --seconds 3
Easy3D renderer: Direct3D 11, vendor=0x10de, device=0x2482
first_world: PASS frames=491 draw_calls=5 visible=4 culled=0 scene_closed=True
# exit code 0
```

The native window, D3D11 device, texture/model resource path, rendered frames,
and teardown all executed on the GUI-capable Windows machine. This timed run
was not separately image-inspected, so exact visual composition is **UNVERIFIED**
rather than inferred from counters.

Ten-second 10,000 shared-cube acceptance workload:

```text
build\venv311\Scripts\python.exe benchmarks\render_cubes.py --count 10000 --seconds 10
requested_instances=10000
creation_seconds=0.1629028000170365
run_seconds=10.03159049997339
frames=3862
overall_fps=384.9838168743276
sample_count=926
frame_ms_median=2.4795
frame_ms_p95=3.0416000000000003
frame_ms_p99=3.2948
renderer: draw_calls=1, visible_instances=9318, culled_instances=682,
          instanced_draw_calls=1
memory: working_set_before=22781952,
        working_set_after_creation=27762688,
        working_set_after_run=77049856,
        peak_working_set_after_run=108290048,
        private_bytes_after_run=83185664
# exit code 0
```

Every requested cube was accounted for (`9318 + 682 == 10000`), and all
visible compatible cubes were submitted as one instanced draw. These figures
describe this exact machine and workload; they are not a general hardware
capacity claim.

Phase 1.10: **DONE**. Immediate next task: Phase 2.1 — native input mapping,
focus/pointer-lock behavior, remappable actions, and headless-testable state.
