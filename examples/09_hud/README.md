# Native HUD

This Phase 6 example renders a 3D scene, alpha-blended panels, a PNG sprite,
Roboto text, an anchored horizontal button stack, hover/pressed states, and
click callbacks through the public RIX API. The overlay is submitted by the
native renderer after the 3D/postprocess passes.

```powershell
python examples/09_hud/main.py
```

Click **Update status** to change the label and **Close** to exit. For a timed
render/lifecycle diagnostic, use `--seconds 5`.
