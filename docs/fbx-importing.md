# FBX importing

RIX loads binary and ASCII FBX directly through the pinned ufbx 0.23.1 native
library. Wheels do not require Autodesk FBX SDK, Blender, or a converter.

```python
import rix

info = rix.load_fbx("assets/YBot.fbx")
print(info.triangle_count, info.skeleton, info.animations, info.warnings)
model = rix.Model("assets/YBot.fbx", collider=False)
```

`ModelCache.load()` dispatches `.fbx`, `.gltf`, `.glb`, and `.obj` through one
canonical cache. FBX import converts source axes and units to RIX's right-handed,
Y-up, metre-based world; triangulates polygons; applies node and geometry
transforms; and imports multiple mesh/material groups, bounds, normals, UVs,
vertex colors, tangents, skeletons, skin clusters, and animation stacks.

Supported material data includes base/diffuse color and texture, normal,
emissive, roughness, metallic and ambient-occlusion maps/factors, and authored
double-sided state. External texture paths use the normal texture cache.
Embedded and layered FBX textures are reported as warnings and use the scalar
material fallback; they are not extracted into hidden files. Unsupported
transparency modes are rendered opaque and warned. Procedural FBX materials,
blend shapes, NURBS, subdivision-at-render-time, constraints, and arbitrary
deformers are not claimed.

Skinning retains the four greatest nonnegative finite influences per vertex,
renormalizes them, and warns when influences are dropped. Invalid indices,
zero totals, nonfinite transforms, excessive hierarchy depth, malformed files,
files over the importer limit, and animation-only files used as visible models
fail with `AssetError`. Use `load_fbx()` to inspect an animation-only asset.

The real-asset audit and source files live with the external animation-test
project rather than in this engine repository.
