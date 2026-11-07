from __future__ import annotations

import rix
from rix import net


CUBE = 1


def registry() -> net.PrefabRegistry:
    result = net.PrefabRegistry(schema_version=107)
    result.register(
        CUBE,
        "cube",
        lambda scene: rix.Cube(
            scene=scene,
            color="orange",
            collider=False,
        ),
    )
    result.register_transform(CUBE)
    return result
