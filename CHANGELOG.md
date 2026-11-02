# Easy3D changelog

All notable private releases are recorded here. Easy3D follows Semantic
Versioning while it remains pre-1.0; the compatibility details and release
procedure are in [docs/release.md](docs/release.md).

## 0.1.0 — 2026-11-01

Initial private Windows x64 release.

- Native C++20 engine and typed Python API with D3D11 rendering through SDL3
  and bgfx.
- Scene/entity lifecycle, assets, cameras, lighting, HUD, audio, physics,
  networking, replication, prediction, multiplayer examples and diagnostics.
- Windows wheels independently tested for CPython 3.11, 3.12 and 3.13 x64.

### Migration notes

This is the first release, so there is no earlier Easy3D release to migrate.
Projects built against development snapshots should recreate their virtual
environment from a `0.1.0` wheel, keep client and server protocol/schema
settings identical, and rerun their own asset and multiplayer smoke tests.
No automated save-game or scene-file migration exists because Easy3D does not
yet define either persisted format.
