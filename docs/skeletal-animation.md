# Skeletal animation

FBX and glTF/GLB use the same native `Skeleton`, `AnimationClip`, pose sampler,
controller, blending, root-motion, and renderer paths. Animation advances once
on the scene's fixed scheduler; normal playback needs no Python update loop.

## Embedded clips

```python
import rix

character = rix.Model("assets/character.fbx", collider=False)
print(character.animation_clips)
character.play(character.animation_clips[0], loop=True, speed=1.0)
```

## A separate FBX animation

```python
character = rix.Model("assets/YBot.fbx", collider=False)
character.add_animation("Thriller", "assets/Thriller Animation.fbx")
character.play("Thriller", loop=True, speed=1.0, blend=0.15)
```

`play()` restarts the named clip. `speed` may be negative for reverse playback
but not zero. `blend` is a nonnegative transition duration in seconds. Use
`pause_animation()`, `resume_animation()`, and `stop_animation()`. Inspect
`current_animation`, `animation_time`, `animation_duration`,
`animation_speed`, `animation_state`, and `animation_skinning` (`"gpu"` or
`"cpu"`). A non-looping completion callback fires once:

```python
character.play("Attack", loop=False, on_complete=lambda model: print("done"))
```

Each visible model owns an independent clock and pose while immutable model,
texture, skeleton, and clip data remain cached/shared. Interrupting a blend
starts from the current displayed local pose. Translation/scale interpolate
linearly and rotations use shortest-path quaternion interpolation.

## Rendering and limits

D3D11/bgfx shaders skin positions, normals, and tangents. Directional, spot,
and all six point-shadow faces use the same animated palette, so shadows follow
the pose. Up to 64 joints use a 3-row-per-joint shader uniform palette; larger
rigs use bounded native C++ transient-buffer CPU skinning. Each model part is
deformed once per frame into a compact layout and reused for every main and
shadow pass. The configured transient bounds are 32 MiB for vertices and 8 MiB
for 32-bit indices. Both paths accept at most four influences per vertex.
`animation_skinning` reports the selected path; RIX never substitutes a static
bind pose. A CPU-fallback frame fails explicitly if the bounded allocation
cannot fit all independently animated parts.

Animated models conservatively bypass bind-pose bounds culling because per-clip
dynamic bounds are not yet generated. This is correct but can cost performance.
Only the committed D3D11 shader backend is verified.

## Root motion and physics

Playback is in-place by default: root drift is removed from the visual pose.
Opt in with `character.play("Walk", root_motion=True)`. RIX applies horizontal
root translation and root yaw to the owner once. Vertical root translation plus
root pitch/roll remain in the animated skeleton so crouches, jumps, and body
lean keep their authored pose without accumulating small loop-seam offsets that
can sink or tilt the entity. The visual root's X/Z translation and yaw are
removed, avoiding double horizontal motion. Root motion is rejected for dynamic rigid
bodies, character controllers, and collider-only static entities; use a
kinematic rigid body when physics ownership is required.

## Pygame

The same API works in a Pygame-owned `World`. Call `world.update(dt)` exactly
once and then `world.render()`; the scheduler advances every controller once.

```python
pygame.init()
screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
world = rix.World(screen)
character = rix.Model(world, "assets/YBot.fbx", collider=False)
character.add_animation("Thriller", "assets/Thriller Animation.fbx")
character.play("Thriller")

while world.running:
    dt = pygame.time.Clock().tick(60) / 1000
    for event in pygame.event.get():
        world.handle_event(event)
    world.update(dt)
    world.render()
world.close()
pygame.quit()
```

Viewports read the same scene/controller state and may use independent cameras;
they do not create a second animation clock or duplicate immutable model data.

The real-asset acceptance test is intentionally stored outside the engine
repository. Run it with:

```powershell
cd "C:\Users\Ryan\Desktop\code\code\python\rix things\animation test"
C:\Users\Ryan\Desktop\code\Easy3D\.venv\Scripts\python.exe main.py
```

Controls are Space pause/resume, R restart, Left/Right rotate, and Escape close.
