# Release, compatibility and distribution

## Versioning

`VERSION` is the single release source for CMake, the native extension, Python
metadata, and `rix.__version__`. Patch releases preserve documented public
behavior where practical; minor releases may add features; major releases may
remove or redesign public APIs.

Networking was removed during the RIX simplification and later reintroduced as
the separately approved optional `rix.net` subsystem. The restored API is not
a compatibility promise for historical `easy3d.network`; applications use the
current Session/transport/replication/state contracts documented in
`features.md` and `docs/networking.md`.

## Release checklist

1. Use an x64 MSVC developer environment.
2. Build Debug and Release native targets and run CTest.
3. Install the editable package and run pytest, mypy, and import/version smoke.
4. Build wheels for Python 3.11, 3.12, 3.13, 3.14, and 3.15 in an x64 MSVC
   environment.
5. Clean-install each wheel with `--no-index`, run `pip check`, import, and tests.
6. Inspect wheel contents for the extension, stubs, `py.typed`, license, and
   notices; reject build-only dependency artifacts.
7. Run interactive window/input/audio/visual smoke tests on Windows.
8. Record exact commands, outputs, artifact hashes, and manual limits.
9. Run independent-process direct-IP and adverse-impairment gates, security
   tests, 2/8/16/32 capacity benchmarks, and verify headless imports do not
   initialize Pygame or graphics.

## Distribution

RIX is licensed under Apache License 2.0. Before publishing an artifact, verify
that its metadata names `Apache-2.0`, that the license and applicable third-
party notices are included, and that only intended runtime files are present.
Publish wheels for the supported Windows/Python combinations after the release
checklist above passes. Keep third-party components under their own licenses.

The final multiplayer/state-system test matrix, artifact hashes, security
result, performance measurements, and limitations are recorded in
`docs/phase16-report.md`.
