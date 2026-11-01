# Easy3D implementation progress

**Current status (2026-11-01): Phase 0 and Phase 1.1–1.2 PASSED; Phase 1.3 is
next.** Earlier blocked checkpoints below are retained as diagnostic history.

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
