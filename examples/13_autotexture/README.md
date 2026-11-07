# AutoTexture and advanced materials

Run from the repository root:

```powershell
.venv\Scripts\python.exe examples\13_autotexture\main.py
```

The scene covers world-scale tiling, shared textures, a generated six-face cube
atlas, spherical mapping, OBJ/glTF authored UVs, tangent-space normal mapping,
and roughness/metallic maps. Close the window normally or press Escape.

Generated, editable assets are written under `examples/13_autotexture/generated`.

Run the real D3D11 resource-lifetime regression with:

```powershell
.venv\Scripts\python.exe tests\manual\autotexture_gpu_lifetime.py
```

It loads shared primitive/model material maps, clears the scene, advances safe
renderer frames, and requires GPU texture count/bytes to return exactly to the
startup baseline.
Edit and save a PNG there while the scene is running to validate hot reload. Use
`--seconds 5` for a bounded automated smoke run; that verifies lifecycle and
prints renderer counters but does not replace human visual inspection.
