# Synchronizing Objects

Define the prefab allow-list in one shared schema module:

```python
import rix
from rix import net

CUBE = 1

def make_registry() -> net.PrefabRegistry:
    registry = net.PrefabRegistry(schema_version=1)
    registry.register(
        CUBE,
        "cube",
        lambda scene: rix.Cube(scene=scene, collider=False),
    )
    registry.register_transform(CUBE)
    return registry
```

The authority assigns the stable object identity and sends transforms:

```python
server = net.Server(port=7777)
server.load_scene(rix.Scene("authority"))
replication = net.ServerReplication(server, make_registry())
cube = replication.spawn(CUBE)
server.start()

while server.state is net.ServerState.LISTENING:
    server.step()
    cube.entity.x += 0.01
    replication.flush_transforms(server.tick_count)
```

The client constructs only that registered prefab:

```python
client = net.Client()
mirror = net.ClientReplication(client, world.scene, make_registry())
client.connect("127.0.0.1", 7777)

while world.running:
    mirror.poll()
    world.update(1 / 60)
    world.render()
```

Add typed values with `registry.register_variable(...)`. Server values are
writable; client mirrors are read-only. Late join, despawn, versions, schema
fingerprints, bounded transform history, baseline recovery, and ownership
cleanup are handled by the replication layer. See
`examples/networking/07_synchronized_cubes` for complete processes.
