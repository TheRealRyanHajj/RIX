"""Python module for the RIX example in examples/networking/11_prediction_interpolation.

This module defines the shared message/state schema imported by the neighboring client
and server examples. Follow the adjacent README to run the example."""

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
