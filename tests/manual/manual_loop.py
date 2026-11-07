"""Visible D3D11 manual-loop smoke; closes automatically after 120 frames."""

import rix as e3


with e3.Game("RIX manual loop smoke", (800, 500), vsync=False) as game:
    cube = e3.Cube(color="orange")
    frames = 0
    while game.running and frames < 120:
        dt = game.tick(120)
        cube.ry += 90 * dt
        frames += 1
    game.stop()

if frames != 120:
    raise RuntimeError(f"manual loop stopped early after {frames} frames")
print("manual loop smoke: PASS (120 frames)")


managed = e3.Game("RIX managed loop regression", (480, 300), vsync=False)
managed.after(0.05, managed.stop)
managed.run()
if managed.frame_count == 0:
    raise RuntimeError("managed loop did not render a frame")
managed.close()
print(f"managed loop smoke: PASS ({managed.frame_count} frames)")


for cycle in range(3):
    with e3.Game(f"RIX lifecycle {cycle + 1}", (320, 240), vsync=False) as repeated:
        repeated.tick(0)
        repeated.stop()
print("repeated lifecycle smoke: PASS (3 games)")
