"""RIX WAV playback and camera-relative positional-audio example."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import struct
import tempfile
import threading
import time
import wave

from rix import AudioSource, Camera, Cube, Entity, Game, Light, Plane, Scene


def _write_tone(path: Path, frequency: float) -> None:
    sample_rate = 48_000
    frame_count = sample_rate // 2
    samples = [
        int(7_500 * math.sin(2.0 * math.pi * frequency * frame / sample_rate))
        for frame in range(frame_count)
    ]
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack(f"<{frame_count}h", *samples))


class MovingEmitter(Cube):
    def __init__(self, source: AudioSource, *, phase: float, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.source = source
        self.phase = phase
        self.elapsed = 0.0

    def update(self, delta_seconds: float) -> None:
        self.elapsed += delta_seconds
        x = math.sin(self.elapsed * 0.8 + self.phase) * 3.5
        self.position = (x, 0.25, 0.0)
        self.source.position = self.position


def run(*, seconds: float | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="rix-audio-") as temporary:
        low_path = Path(temporary) / "low.wav"
        high_path = Path(temporary) / "high.wav"
        _write_tone(low_path, 330.0)
        _write_tone(high_path, 550.0)

        game = Game("RIX — Positional Audio", (960, 540), vsync=True)
        low = game.audio.play(
            game.audio.load(low_path),
            loop=True,
            volume=0.55,
            position=(-3.5, 0.25, 0),
            maximum_distance=14,
        )
        high = game.audio.play(
            game.audio.load(high_path),
            loop=True,
            volume=0.45,
            position=(3.5, 0.25, 0),
            maximum_distance=14,
        )

        scene = Scene("Audio example")
        camera = Camera(position=(0, 3.2, 8))
        camera.look_at((0, 0, 0))
        scene.camera = camera
        with scene:
            Light("ambient", intensity=0.3)
            Light("directional", rotation=(-35, -25, 0))
            Plane(position=(0, -0.8, 0), size=(12, 8), color=(0.15, 0.19, 0.28))
            MovingEmitter(
                low, phase=-math.pi / 2, size=0.9, color=(0.2, 0.55, 1.0)
            )
            MovingEmitter(
                high, phase=math.pi / 2, size=0.9, color=(1.0, 0.35, 0.2)
            )
        scene.hud.text(
            "Two looping mono WAV sources move across the listener",
            position=(24, 24),
            font_size=22,
        )
        game.load_scene(scene)

        backend_seen = threading.Event()

        class BackendObserver(Entity):
            def update(self, _delta_seconds: float) -> None:
                if game.audio.available:
                    backend_seen.set()

        with scene:
            observer = BackendObserver("audio backend observer")

        if seconds is not None:
            threading.Thread(
                target=lambda: (time.sleep(seconds), game.stop()), daemon=True
            ).start()
        try:
            game.run()
        finally:
            low.stop()
            high.stop()
            observer.destroy()

        if not backend_seen.is_set():
            raise RuntimeError("SDL3 did not activate a native playback device")
        print(
            "audio_example: PASS "
            f"frames={game.frame_count} sounds={game.audio.sound_count} "
            "backend=SDL3"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=None)
    arguments = parser.parse_args()
    if arguments.seconds is not None and arguments.seconds <= 0:
        parser.error("--seconds must be positive")
    run(seconds=arguments.seconds)


if __name__ == "__main__":
    main()
