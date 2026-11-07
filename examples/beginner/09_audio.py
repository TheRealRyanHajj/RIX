"""Load and play a PCM16 WAV supplied on the command line."""

from pathlib import Path
import sys

from rix import Game, Text


if len(sys.argv) != 2:
    raise SystemExit("usage: python examples/beginner/09_audio.py path/to/sound.wav")
game = Game("Audio")
sound = game.audio.load(Path(sys.argv[1]))
game.audio.play(sound, loop=True, volume=0.7)
Text("Playing a native SDL3 audio voice", x=20, y=20)
game.run()
