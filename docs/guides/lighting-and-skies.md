# Lighting and skies

RIX lights are ordinary entities: move them with `position`, aim them with
`rotation` or `look_at()`, toggle them with `enabled`, and change their values
while the game runs. Skies belong to scenes and never enter physics, picking,
or the entity hierarchy.

## 1. Add a sky

Every scene starts with a procedural sky. Restore or disable it explicitly:

```python
import rix as e3

game = e3.Game("Sky")
game.skybox = "default"
# game.skybox = None  # clear-color background instead
game.run()
```

## 2. Change sky colors

```python
game.skybox = e3.Skybox(
    top="skyblue",
    horizon="lightblue",
    bottom="#101624",
    brightness=0.9,
)
game.skybox.rotation = 15
```

The fullscreen sky follows camera rotation but ignores camera translation. It
is drawn behind geometry into the same post-processing target.

## 3. Use a sky panorama or cubemap

```python
game.skybox = "assets/sky.png"  # exact 2:1 equirectangular panorama
game.skybox = e3.Skybox(cubemap="assets/skybox")
```

A missing panorama creates a bounded 2048x1024 PNG. A missing cubemap folder
creates seamless starter-gradient `right.png`, `left.png`, `top.png`,
`bottom.png`, `back.png`, and `front.png` faces at 512x512. An explicit mapping
with those six keys is also accepted. RIX never overwrites an existing
image; malformed or differently sized authored faces produce an actionable
error.

## 4. Make indoor point lights

```python
lamp = e3.Light(
    "point", position=(0, 3, 0), color="orange",
    intensity=5, range=12,
)

@game.update
def pulse(dt):
    lamp.position = (lamp.x, 3, lamp.z)
```

Point lights use a smooth range cutoff plus inverse-square-like attenuation.
For ordinary animation, assign `position`, `color`, `intensity`, or `range`
directly; no shader update call is required.

## 5. Create a flashlight spotlight

```python
flashlight = e3.Light(
    "spot", position=(0, 2, 4), color="white",
    intensity=8, range=20, inner_angle=24, angle=35,
)
flashlight.look_at((0, 1, 0))
```

`angle` and `inner_angle` are full cone angles. Illumination fades smoothly
between the inner and outer cones and at the configured range.

## 6. Combine multiple lights

```python
e3.Light("ambient", color="#607090", intensity=0.15)
e3.Light("directional", rotation=(-45, 0, 0), intensity=1)
e3.Light("directional", rotation=(30, 90, 0), color="blue", intensity=0.3)
e3.Light("point", position=(-3, 2, 0), color="red", intensity=6)
e3.Light("point", position=(3, 2, 0), color="green", intensity=6)
```

The first explicit ambient or directional light replaces that kind's beginner
defaults. The automatic directional defaults are a warm key and weaker cool
fill, which preserve face contrast around an object; later explicit lights
supplement the first custom source. `scene.lights()` returns the registered
lights, optionally filtered by kind.

## 7. Configure shadows

```python
sun = e3.Light("directional", casts_shadows=True, shadow_resolution=2048)
lamp = e3.Light(
    "point", position=(0, 4, 0), casts_shadows=True,
    shadow_resolution=512, shadow_bias=0.002,
)
flashlight.casts_shadows = True
flashlight.shadow_resolution = 1024
```

Resolution zero selects the preset default; explicit values are powers of two
from 128 through 8192. Point lights do not cast by default because one point
shadow requires six render passes. High and Ultra admit at most one
directional, one point, and one spot shadow caster per frame. Additional
requests remain valid lights and are reported as dropped shadow casters.

## 8. Keep lighting fast

Low/Medium/High/Ultra admit `1/4/2`, `2/16/8`, `4/32/16`, and `4/64/32`
directional/point/spot lights. Native frustum/cone culling and stable priority
choose the active set. Inspect the result without doing Python-side lighting:

```python
stats = game.renderer_stats
print(stats.active_point_lights, stats.culled_lights)
print(stats.shadow_passes, stats.shadow_memory_bytes)
```

Use the live demo and repeatable stress benchmark:

```powershell
python examples\15_lighting_sky\main.py --sky procedural
python examples\15_lighting_sky\main.py --sky panorama
python examples\15_lighting_sky\main.py --sky cubemap
python benchmarks\lighting.py --directional-lights 4 --point-lights 64 --spot-lights 32
```
