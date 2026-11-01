# Easy3D implemented API contract

## Scene and entity lifecycle

```python
from easy3d import Entity, Game, Scene

scene = Scene("main")
with scene:
    player = Entity("player")
    prop = Entity("prop")

game = Game("Example")
game.load_scene(scene)

assert player.is_alive
player.enabled = False
prop.destroy()

game.unload_scene()
scene.close()
```

Outside a `with scene:` block, pass `scene=...` or call
`scene.create_entity()`. Easy3D deliberately raises an actionable `RuntimeError`
instead of selecting an unqualified global world.

`Entity.destroy()` invalidates every wrapper to that entity. `Scene.clear()`
invalidates all current entities but leaves the scene reusable. `Scene.close()`
clears and permanently closes it. Access through a stale wrapper raises
`InvalidEntityError`, which is a Python `ReferenceError` subclass:

```python
from easy3d import InvalidEntityError

entity = scene.create_entity()
entity.destroy()

try:
    print(entity.name)
except InvalidEntityError:
    pass
```

Implemented entity properties include `id`, `name`, `enabled`, `visible`,
`scene`, `is_alive`, local/world transforms, `parent`, and `children`.
`MeshRenderer` is the first singleton native component and is available through
typed `has_component`, `get_component`, and `remove_component`. Physics and
network identity remain later checklist items.

## Renderable entities and components

```python
from easy3d import Cube, MeshRenderer, Model, Plane, Scene, Sphere

world = Scene("world")
with world:
    floor = Plane(size=(20, 20), color=(0.3, 0.35, 0.4))
    cube = Cube(position=(0, 0.5, 0), texture="assets/crate.png")
    ball = Sphere(position=(2, 0.5, 0), radius=0.5)
    prop = Model("assets/prop.obj", position=(-2, 0, 0))

renderer = cube.get_component(MeshRenderer)
assert renderer is not None
renderer.color = (0.8, 0.9, 1.0)
renderer.lit = False
```

`Cube`, `Plane`, `Sphere`, and `Model` are normal subclassable `Entity` values
that transactionally attach one native `MeshRenderer`. Construction failures
destroy the partially created entity. Primitive mesh allocations and parsed OBJ
assets are shared across instances; the private renderer also shares GPU buffers
by immutable resource identity. A primitive texture is decoded/cached at
construction. OBJ parts apply their MTL diffuse color and optional diffuse map.

Primitive dimensions are expressed through entity scale: cube `size` accepts a
positive scalar or XYZ tuple, plane `size` a scalar or width/depth tuple, and
sphere `radius` a positive scalar. `MeshRenderer.color` is multiplicative RGBA
with finite components in `[0,1]`; `kind` and `asset` are read-only, and
`lit` selects baseline ambient/directional lighting versus unlit vertex/material
color, and `remove()` detaches the component.

The loaded scene is traversed natively for every rendered frame. No per-entity
Python draw calls occur. The renderer reads the scene-owned camera, native light
components, and render components during that traversal. Public
scene/entity/component mutation raises `RuntimeError` while `Game.run()` is
active because the Phase 2 safe-boundary scheduler is not implemented yet.

## Math and transform conventions

`Vec2` and `Vec3` provide finite components, arithmetic, dot products,
normalization, and explicit approximate comparison. `Vec3` also provides cross
products. `Quat` is stored as `(w, x, y, z)` and supports normalization,
multiplication, vector rotation, and degree-based Euler conversion.

Entity `position`, `rotation`, and `scale` are local-space live properties:
`entity.position.x += 1` writes through to native state. `world_position`,
`world_rotation`, `world_quaternion`, and `world_scale` are calculated snapshots.
The coordinate system is right-handed, +Y up, with camera-forward -Z. Euler
angles are degrees and are not unique: reading a rotation may produce a different
but orientation-equivalent triple. Compare quaternions when orientation identity
matters.

`entity.set_parent(parent, keep_world=False)` preserves the local transform by
default. Pass `keep_world=True` to recompute local TRS while preserving the
current world transform. Parenting rejects self-parenting, cycles, stale handles,
and cross-scene relationships. Destroying a parent detaches its direct children
while preserving their world transforms.

## Camera configuration

```python
from easy3d import Camera

camera = Camera(
    position=(0, 3, 8),
    vertical_fov_degrees=60,
    near_plane=0.1,
    far_plane=500.0,
)
camera.look_at((0, 0, 0))
scene.camera = camera
view = camera.view_matrix()
projection = camera.projection_matrix((1280, 720))
```

`Camera` is right-handed with local forward -Z and uses degree-based public
Euler rotation backed by native quaternion math. FOV must be strictly between
0° and 180°; near must be positive; far must exceed near. Projection matrices
are column-major. D3D-style projection maps depth to `[0,1]`; the explicit
`homogeneous_depth=True` query maps it to `[-1,1]` for backend testing.

`Camera.aspect_ratio((width, height))` and `projection_matrix` reject zero or
non-integer dimensions. The renderer uses current SDL pixel dimensions after
every resize. Assigning `scene.camera` copies the current camera value into the
native scene. Reading `scene.camera` returns a detached typed copy; change it and
assign it back when updating several fields. Cameras are scene values rather
than entity components in this baseline.

## Lighting, materials, and debug lines

```python
from easy3d import Cube, Light, Scene, debug

scene = Scene("lit world")
with scene:
    Light("ambient", color=(0.5, 0.6, 1.0), intensity=0.2)
    sun = Light("directional", intensity=0.9, rotation=(-35, -30, 0))
    lit_cube = Cube(position=(-1, 0, 0), color=(0.9, 0.2, 0.1))
    unlit_cube = Cube(position=(1, 0, 0), color=(0.2, 0.9, 0.3), lit=False)
    debug.axes(size=2.0)
    debug.line((-2, 0, 0), (2, 0, 0), depth_test=False)
```

`Light` owns one native `LightComponent`. Ambient light colors are multiplied by
intensity and accumulated. The first enabled directional light supplies its
world-space local -Z direction and color/intensity; additional directional
lights are retained as components but not blended by this baseline. If a scene
has no explicit light of a kind, the renderer keeps its corresponding usable
default ambient or directional contribution. Disabled light entities are
ignored. Light color components are finite in `[0,1]`; intensity is finite and
non-negative.

Baseline lit materials apply diffuse Lambert lighting to both solid and
textured RGB while retaining material alpha. Normals use the inverse-transpose
world transform, so non-uniformly scaled objects remain correct. There are no
shadows, specular/PBR channels, transparent sorting, or gamma-adjustable light
units yet. Pass `lit=False` during primitive/model construction or set
`MeshRenderer.lit` before running the game for unlit color.

`debug.line` and `debug.axes` append persistent native scene lines. Depth-tested
and overlay lines are batched separately into frame-local transient GPU buffers.
They persist until `scene.clear_debug_lines()` or `scene.clear()`; debug drawing
does not create entities and does not cross into Python once per rendered frame.

## Renderer visibility and counters

```python
game.run()
print(game.renderer_stats)
# RendererStats(draw_calls=..., visible_instances=..., culled_instances=...,
#               instanced_draw_calls=...)
```

Before submission, the renderer tests a conservative transformed bounding sphere
derived from each mesh's cached local AABB against the current scene-camera
frustum. `visible_instances` and `culled_instances` count mesh parts, so a
multi-part OBJ may contribute more than one. Disabled, invisible, and
non-renderable entities contribute neither. `draw_calls` counts submitted 3D
and debug batches; `instanced_draw_calls` is the subset using instance data.

Visible items with identical mesh, material state/color, and texture/sampler are
grouped. Two or more compatible items with uniform absolute XYZ scale use one or
more bgfx instance buffers; non-uniformly scaled items fall back to individual
draws to preserve exact inverse-transpose normals. `Game.renderer_stats` returns
a coherent, immutable `RendererStats` snapshot from the latest completed frame
and is safe to sample from a monitoring thread while `Game.run()` has released
the GIL.

## Texture assets

```python
from easy3d.assets import TextureCache, load_image

info = load_image("assets/albedo.jpg", color_space="srgb")
cache = TextureCache()
shared = cache.load("assets/albedo.jpg")
assert len(cache) == 1
```

`load_image` accepts `.png`, `.jpg`, and `.jpeg`, decodes to four-channel
RGBA8 storage, and returns immutable metadata. `TextureCache` owns shared native
image resources and uses a deterministic canonical-path plus color-space key;
`clear()` drops cache ownership without invalidating already referenced native
resources. Cache access is thread-safe. It is intentionally synchronous until
the later asynchronous asset milestone.

Color textures default to `srgb`; data textures can request `linear`. Public
mesh UV `(0, 0)` refers to the first/top-left decoded texel, `u` increases right,
and `v` increases down. Native `TextureSampler` supports linear/nearest min,
mag, and mip choices plus repeat/clamp U/V modes. The current D3D11 diagnostic
visibly validates nearest sampling and repeat defaults. GPU cache identity
includes both the immutable decoded image and sampler settings.

A missing/non-file path raises `MissingAssetError`, an `AssetError` subclass.
Malformed files and unsupported extensions raise `AssetError` with the path and
decoder context. The public API never exposes bgfx handles.

Graphics-disabled/headless builds retain the asset types and deterministic error
surface but deliberately do not link image decoders; attempting image decode in
that configuration raises `AssetError`. Dedicated servers do not need texture
pixels. A future headless content-validation tool may split decoding into a
separate optional build feature if that becomes a concrete requirement.

## OBJ model assets

```python
from easy3d.assets import ModelCache, load_obj

model = load_obj("assets/house.obj")
cache = ModelCache()
shared = cache.load("assets/house.obj")
```

The OBJ importer preserves positions, normalized supplied normals, texture
coordinates, and optional per-vertex RGB. Faces are triangulated. If any corner
of a triangle lacks a normal, Easy3D creates a flat geometric normal and unique
vertices for that triangle. Degenerate triangles are rejected. OBJ V is flipped
(`v_engine = 1 - v_obj`) into Easy3D's top-left texture convention; U is
unchanged. Shapes are split again by material so every `ModelPartInfo` has one
material index.

`ModelCache` is thread-safe, holds immutable native model/mesh data, and uses a
canonical path key. `Model` entities reference that shared data rather than
parsing or copying the model again.
Clearing the cache does not invalidate outstanding native shared references.
OBJ loading and caching work in graphics-disabled/headless builds.

Supported MTL fields are material name, diffuse `Kd`, dissolve `d`/`Tr`, and
diffuse texture `map_Kd`. Diffuse texture paths are currently resolved relative
to the OBJ directory; keep MTL files and their referenced textures under that
root. Missing MTL files, unknown material names, missing diffuse textures,
invalid indices, empty geometry, and malformed files are errors. Other MTL
channels/options (specular/normal maps, illumination models, PBR extensions,
multiple texture layers) are parsed by the dependency where possible but not
represented or claimed by Easy3D. Smoothing-group normal generation is not yet
implemented: provide normals for smooth shading, otherwise output is flat.
