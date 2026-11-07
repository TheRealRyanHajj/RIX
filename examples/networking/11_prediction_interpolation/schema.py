from __future__ import annotations

import rix
from rix import net


AVATAR = 1


def registry() -> net.PrefabRegistry:
    result = net.PrefabRegistry(schema_version=111)
    result.register(
        AVATAR,
        "remote_avatar",
        lambda scene: rix.Cube(
            scene=scene,
            color="#f59e0b",
            size=(0.8, 1.8, 0.8),
            collider=False,
        ),
    )
    result.register_transform(AVATAR)
    return result
