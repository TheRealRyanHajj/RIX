"""Procedural and image skybox forms."""

# Usage: from the repository root, run:
#   python examples/beginner/12_skyboxes.py

from rix import Game, Skybox

game = Game(graphics_preset="high")
game.skybox = Skybox(
    top="skyblue", horizon="lightblue", bottom="#101624", brightness=1.1
)

# A missing panorama is generated safely, then loaded as a 2:1 sky:
# game.skybox = "assets/my_sky.png"
# A missing six-face folder generates right/left/top/bottom/front/back PNGs:
# game.skybox = Skybox(cubemap="assets/my_cubemap")
# Disable it with: game.skybox = None

game.run()
