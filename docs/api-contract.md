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
`scene`, `is_alive`, local/world transforms, `parent`, and `children`. Component
attachment, scene-to-renderer submission, physics, and network identity are
later checklist items and are not available yet. The native renderer does have
validated mesh/material data and indexed D3D11 submission, but Phase 1.3 does
not expose premature Python primitive APIs.

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
every resize. This standalone camera is not yet attached to an entity or loaded
scene; that is intentionally deferred to the render-component milestone.

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
visibly validates nearest sampling and repeat defaults; scene material exposure
arrives with render components.

A missing/non-file path raises `MissingAssetError`, an `AssetError` subclass.
Malformed files and unsupported extensions raise `AssetError` with the path and
decoder context. The public API never exposes bgfx handles.

Graphics-disabled/headless builds retain the asset types and deterministic error
surface but deliberately do not link image decoders; attempting image decode in
that configuration raises `AssetError`. Dedicated servers do not need texture
pixels. A future headless content-validation tool may split decoding into a
separate optional build feature if that becomes a concrete requirement.
