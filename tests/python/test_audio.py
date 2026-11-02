from __future__ import annotations

import struct
from pathlib import Path
import wave

import pytest

from easy3d import AudioSource, Game, Sound, Vec3


def _wav(path: Path, *, width: int = 2, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(48_000)
        if width == 2:
            sample_count = 48 * channels
            output.writeframes(
                struct.pack("<" + "h" * sample_count, *([8192] * sample_count))
            )
        else:
            output.writeframes(bytes([128] * (48 * channels)))


def test_wav_load_cache_metadata_and_playback_controls(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _wav(path)
    game = Game()
    sound = game.audio.load(path)
    assert isinstance(sound, Sound)
    assert game.audio.load(path) is sound
    assert sound.channels == 1
    assert sound.sample_rate == 48_000
    assert sound.frame_count == 48
    assert sound.duration == pytest.approx(0.001)
    assert game.audio.sound_count == 1
    assert not game.audio.available

    source = game.audio.play(
        sound,
        volume=0.5,
        loop=True,
        position=(2.0, 0.0, 0.0),
        minimum_distance=1.0,
        maximum_distance=10.0,
    )
    assert isinstance(source, AudioSource)
    assert source.playing and source.loop and source.spatial
    assert source.volume == 0.5
    assert source.position == Vec3(2.0, 0.0, 0.0)
    source.volume = 0.25
    source.position = Vec3(-2.0, 1.0, 0.0)
    assert source.volume == 0.25
    assert source.position == Vec3(-2.0, 1.0, 0.0)
    assert game.audio.active_voice_count == 1
    source.stop()
    source.stop()
    assert not source.playing
    assert game.audio.active_voice_count == 0


def test_audio_rejects_bad_assets_and_cross_game_sounds(tmp_path: Path) -> None:
    missing = tmp_path / "missing.wav"
    with pytest.raises(FileNotFoundError):
        Game().audio.load(missing)

    eight_bit = tmp_path / "8bit.wav"
    _wav(eight_bit, width=1)
    with pytest.raises(ValueError, match="16-bit"):
        Game().audio.load(eight_bit)

    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not a wave")
    with pytest.raises(ValueError, match="invalid WAV"):
        Game().audio.load(broken)

    valid = tmp_path / "valid.wav"
    _wav(valid, channels=2)
    first = Game()
    second = Game()
    sound = first.audio.load(valid)
    with pytest.raises(ValueError, match="this game's"):
        second.audio.play(sound)


def test_audio_validates_public_controls(tmp_path: Path) -> None:
    path = tmp_path / "tone.wav"
    _wav(path)
    audio = Game().audio
    sound = audio.load(path)
    with pytest.raises(ValueError, match="volume"):
        audio.play(sound, volume=-1)
    with pytest.raises(TypeError, match="loop"):
        audio.play(sound, loop=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="distance"):
        audio.play(sound, position=(0, 0, 0), minimum_distance=10, maximum_distance=1)
    with pytest.raises(ValueError):
        audio.play(sound, position=(float("nan"), 0, 0))
