# Moving Objects

Every object has simple position and rotation properties:

```python
import rix as e3

game = e3.Game()
cube = e3.Cube()
cube.x = 2
cube.y += 1
cube.ry = 45
cube.position = (1, 2, 3)
```

Helpers accept either a tuple or three numbers:

```python
cube.move(0, 0, -1)
cube.rotate(0, 90, 0)
cube.look_at((0, 1, 0))
```

For persistent simulation motion, every entity accepts and exposes four live
world-space vectors:

```python
cube = e3.Cube(
    collider=False,                         # ordinary native motion, no static body
    velocity=(0, 0, -5),                 # world units / second
    acceleration=(0, -9.81, 0),          # world units / second squared
    angular_velocity=(0, 90, 0),          # degrees / second
    angular_acceleration=(0, -15, 0),     # degrees / second squared
)

cube.velocity.x += 2
print(cube.speed, cube.movement_direction)
```

RIX integrates ordinary entities on the native fixed clock with
semi-implicit Euler. Linear and angular values remain world-space even when an
entity has a transformed parent. Velocity does not automatically change which
way an object faces.

Use the orientation helpers to convert or query directions:

```python
print(cube.forward, cube.right, cube.up)
world_direction = cube.local_to_world_direction((0, 0, -1))
local_direction = cube.world_to_local_direction(world_direction)
cube.face_direction((1, 0, -1))
cube.launch((1, 0.2, -1), 20, face=True)
```

Setting `speed` rescales the current velocity. At rest, a positive speed starts
motion along `forward`. Speeds must be finite and non-negative; launch/facing
directions must be nonzero.

`Player.view_forward`, `view_right`, and `view_up` include camera look. The
inherited `forward`, `right`, and `up` remain body-facing vectors. A typical
camera-aimed projectile is:

```python
bullet = e3.Sphere(
    position=player.world_position + player.view_forward,
    physics=True,
    continuous=True,
)
bullet.launch(player.view_forward, 40, face=True)
```

Move something procedurally in an update callback by multiplying by `dt` when
the motion is not persistent simulation state:

```python
@game.update
def update(dt):
    cube.ry += 90 * dt

game.run()
```

Dynamic physics bodies are owned by physics during simulation. Use forces,
impulses, the universal motion properties, character movement, or `teleport()`
instead of assigning their transform directly. Jolt owns actual rigid-body
linear/angular velocity; RIX adds acceleration each fixed step. Characters
accept linear velocity and acceleration but remain upright, so only Y angular
motion is valid.

`teleport(position, rotation=None)` preserves all motion. Pass
`reset_motion=True` to clear velocity, acceleration, angular velocity, and
angular acceleration. Disabling an entity freezes and snapshots motion;
re-enabling resumes it. A collider without a Rigidbody is static and rejects
nonzero motion. Because world geometry is collidable by default, pass
`collider=False` for a visual moved by these vectors, or attach a kinematic
Rigidbody for a moving obstacle.

For a short transition, use the managed tween convenience:

```python
cube.animate("y", to=5, duration=1, easing="ease_in_out")
```
