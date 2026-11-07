# RIX developer-experience audit

## Strengths

- One typed top-level package with beginner primitives and explicit escape
  hatches.
- Default game/scene/camera/light setup for first-run success.
- Remappable input and a self-driving first-/third-person player.
- Native physics, rendering, audio, UI, asset caches, and diagnostics behind
  compact Python APIs.
- Focused examples and strict automated coverage.

## Current friction

- Native editable installs require an MSVC developer shell.
- First configure downloads pinned source dependencies and can be slow.
- Interactive visual/input/audio validation is inherently manual.
- The glTF runtime renderer does not yet apply sampled skeletal animation.
- HUD typography and layout remain intentionally basic.

## Simplified scope

Removing networking eliminates a large expert-only API, several heavy native
dependencies, online configuration, port/firewall troubleshooting, duplicated
authority concepts, and a broad test/benchmark matrix. Documentation and
examples can now teach one local ownership model from beginner to advanced use.

## Next improvements

- Add a small environment diagnostic command for compiler and runtime setup.
- Continue tuning player movement with interactive obstacle-course evidence.
- Add GPU skinning for the existing glTF skeleton/animation data.
- Improve asset error messages and optional editor-style inspection tools.
