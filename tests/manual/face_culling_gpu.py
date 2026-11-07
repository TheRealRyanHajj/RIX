"""Real-D3D11 culling and instancing probe; not a headless pytest."""

import rix as e3


def tick_frames(game: e3.Game, count: int) -> None:
    for _ in range(count):
        game.tick(240)


game = e3.Game(
    "RIX culling GPU probe",
    (800, 450),
    vsync=False,
    graphics_preset="low",
    auto_setup=False,
)
scene = e3.Scene("Culling batches")
scene.skybox = None
camera = e3.Camera(position=(0, 2, 10))
camera.look_at((0, 0, 0))
scene.camera = camera
with scene:
    e3.Cube(x=-2.5, color="cyan", double_sided=True, collider=False)
    e3.Cube(x=0, color="cyan", double_sided=True, collider=False)
    mutable = e3.Cube(x=2.5, color="cyan", collider=False)
game.load_scene(scene)

with game:
    tick_frames(game, 20)
    separated = game.renderer_stats
    if separated.draw_calls != 2 or separated.instanced_draw_calls != 1:
        raise RuntimeError(
            "different cull modes did not form two batches: "
            f"draws={separated.draw_calls} instanced={separated.instanced_draw_calls}"
        )

    mutable.double_sided = True
    tick_frames(game, 20)
    merged = game.renderer_stats
    if merged.draw_calls != 1 or merged.instanced_draw_calls != 1:
        raise RuntimeError(
            "identical cull modes did not merge after runtime mutation: "
            f"draws={merged.draw_calls} instanced={merged.instanced_draw_calls}"
        )

    print(
        "face_culling_gpu: PASS "
        f"separated={separated.draw_calls}/{separated.instanced_draw_calls} "
        f"merged={merged.draw_calls}/{merged.instanced_draw_calls}"
    )
