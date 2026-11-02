# Release, compatibility and private distribution

## Version source and release numbering

`VERSION` is the only editable engine/package release version. It must contain
one `MAJOR.MINOR.PATCH` value. The build backend derives wheel metadata from it;
CMake derives `PROJECT_VERSION` and the native `engine_version()` value from the
same file; installed Python derives `easy3d.__version__` from distribution
metadata. Tests require all three values to match.

Easy3D uses Semantic Versioning with these pre-1.0 rules:

- `PATCH` fixes defects without intentionally breaking documented Python API,
  supported assets, or protocol behavior.
- `MINOR` may change documented API while the project is pre-1.0. Every such
  change requires explicit migration notes in `CHANGELOG.md`.
- `MAJOR` is reserved for the eventual stable compatibility contract.

Release versions are final numeric versions. Pre-release spellings are not yet
part of the release process. Never edit CMake, Python or wheel version strings
independently; change `VERSION` and add a changelog section in the same commit.

## Compatibility contract

| Boundary | Current contract |
| --- | --- |
| Operating system | Windows 10/11 x64 only |
| Python runtime | CPython 3.11, 3.12 and 3.13 x64; exact ABI-tagged wheels |
| Python API | Patch-compatible documented public API; minor releases may require documented migration before 1.0 |
| Native C++ ABI | Private and unstable; never replace or mix `.pyd`/DLL files between wheels |
| Application protocol | Exact match, currently `1`; mismatch is rejected with code `1001` |
| Application schema | Nonzero game-owned integer; exact match, mismatch is rejected with code `1002` |
| Replication registry | Schema version and canonical fingerprint must match before state is accepted |
| Discovery wire format | Internal exact-match format `1` |
| Replication wire format | Internal exact-match format `2` |
| Persisted saves/scenes | No engine-owned persisted format or compatibility promise yet |

Engine release versions do not silently substitute for network compatibility
versions. A patch release that leaves protocol/schema formats unchanged can
interoperate only when the game intentionally uses the same application
protocol, schema and prefab registry. A format change must increment the
appropriate protocol or game schema version and ship coordinated clients and
servers. See `docs/network-protocol.md` for the actual frames and rejection
behavior.

Third-party native libraries are statically/private linked or bundled as part
of a complete wheel. Their ABI is not a consumer boundary. Asset compatibility
is limited to the documented PNG/JPEG, OBJ/MTL, bounded glTF/GLB and PCM16 WAV
subsets; unsupported constructs fail explicitly rather than becoming a version
compatibility promise.

## Release checklist

1. Start from a clean tracked worktree and review `CHANGELOG.md` migration notes.
2. For a new release, update only `VERSION`, then add the matching changelog
   section and documentation changes.
3. Open an x64 Visual Studio developer PowerShell and run
   `scripts/build_wheel_matrix.ps1`. Do not add a Python classifier or artifact
   unless that exact interpreter completes the clean install and full suite.
4. Run the final regression, packaging, soak and performance commands recorded
   in `docs/progress.md`; investigate regressions instead of moving budgets.
5. Inspect each wheel for the native `.pyd`, `_easy3d.pyi`, `py.typed`,
   `LICENSE` and `LICENSES/THIRD_PARTY.md`. Record file sizes and SHA-256 values.
6. Stage immutable wheels and a checksum manifest in a versioned private
   artifact directory. Install one staged wheel into a new environment and
   rerun the import/version smoke before granting consumers access.
7. Tag/source-control policy and any upload remain an explicit owner action;
   the build script does not push, publish, or modify global tools.

## Private artifact distribution

The simplest supported channel is an access-controlled SMB directory whose
contents are immutable after validation:

```text
\\private-share\easy3d\0.1.0\
  easy3d-0.1.0-cp311-cp311-win_amd64.whl
  easy3d-0.1.0-cp312-cp312-win_amd64.whl
  easy3d-0.1.0-cp313-cp313-win_amd64.whl
  SHA256SUMS.txt
```

The matrix script writes `build\wheelhouse\SHA256SUMS.txt` with the hashes it
computed through .NET's SHA-256 implementation. Review it before copying:

```powershell
Get-Content build\wheelhouse\SHA256SUMS.txt
```

Consumers select the wheel by their interpreter without native build tools or
internet access:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links \\private-share\easy3d\0.1.0 easy3d==0.1.0
.\.venv\Scripts\python.exe -c "import easy3d; print(easy3d.engine_version())"
```

An authenticated PEP 503-compatible private index may replace the file share,
but the same immutable files, hashes, access controls and exact-version pins
apply. Do not publish these proprietary wheels to PyPI or a public release.
Retain the previous versioned directory for rollback; rollback means creating a
new environment with the prior complete wheel, never copying an old `.pyd` into
a newer package.

## 0.1.0 migration

`0.1.0` is the initial private release and has no predecessor. The complete
initial notes are in `CHANGELOG.md`. Future releases must describe renamed or
removed APIs, protocol/schema changes, asset changes, manual data conversions
and a tested rollback path here or in the linked changelog entry.
