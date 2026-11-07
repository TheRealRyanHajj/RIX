"""Decoded sound assets and native playback voices."""

from __future__ import annotations

import math
from pathlib import Path
import wave

from ._rix import Engine
from .math import Vec3


def _volume(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("volume must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 4.0:
        raise ValueError("volume must be finite and in [0, 4]")
    return result


class Sound:
    """An immutable, decoded PCM sound owned by one :class:`Audio` manager."""

    __slots__ = ("_audio", "_id", "_path", "_channels", "_sample_rate", "_frames")

    def __init__(
        self,
        audio: Audio,
        sound_id: int,
        path: Path,
        channels: int,
        sample_rate: int,
        frames: int,
    ) -> None:
        self._audio = audio
        self._id = sound_id
        self._path = path
        self._channels = channels
        self._sample_rate = sample_rate
        self._frames = frames

    @property
    def path(self) -> Path:
        return self._path

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def frame_count(self) -> int:
        return self._frames

    @property
    def duration(self) -> float:
        return self._frames / self._sample_rate


class AudioSource:
    """A currently playing native voice; position and gain may be changed live."""

    __slots__ = ("_audio", "_id", "_volume", "_position", "_spatial", "_loop")

    def __init__(
        self,
        audio: Audio,
        voice_id: int,
        volume: float,
        position: Vec3,
        spatial: bool,
        loop: bool,
    ) -> None:
        self._audio = audio
        self._id = voice_id
        self._volume = volume
        self._position = position
        self._spatial = spatial
        self._loop = loop

    @property
    def playing(self) -> bool:
        return self._audio._engine.audio_voice_playing(self._id)

    @property
    def loop(self) -> bool:
        return self._loop

    @property
    def spatial(self) -> bool:
        return self._spatial

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        result = _volume(value)
        self._audio._engine.audio_set_volume(self._id, result)
        self._volume = result

    @property
    def position(self) -> Vec3:
        return Vec3.from_value(self._position)

    @position.setter
    def position(self, value: Vec3 | tuple[float, float, float]) -> None:
        position = Vec3.from_value(value)
        self._audio._engine.audio_set_position(self._id, tuple(position))
        self._position = position

    def stop(self) -> None:
        """Stop playback. Calling this more than once is harmless."""

        self._audio._engine.audio_stop(self._id)


class Audio:
    """Game-local WAV asset cache and native playback entry point."""

    __slots__ = ("_engine", "_sounds")

    _MAX_DECODED_BYTES = 256 * 1024 * 1024

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._sounds: dict[Path, Sound] = {}

    def load(self, path: str | Path) -> Sound:
        """Load an uncompressed 16-bit mono/stereo WAV, cached by resolved path."""

        source = Path(path).expanduser().resolve()
        cached = self._sounds.get(source)
        if cached is not None:
            return cached
        if not source.is_file():
            raise FileNotFoundError(source)
        try:
            with wave.open(str(source), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.getnframes()
                compression = wav.getcomptype()
                decoded_size = frames * channels * sample_width
                if compression != "NONE":
                    raise ValueError("only uncompressed PCM WAV files are supported")
                if channels not in (1, 2):
                    raise ValueError("WAV audio must be mono or stereo")
                if sample_width != 2:
                    raise ValueError("WAV audio must use 16-bit PCM samples")
                if not 8_000 <= sample_rate <= 192_000:
                    raise ValueError("WAV sample rate must be in [8000, 192000]")
                if frames == 0:
                    raise ValueError("WAV audio must contain at least one frame")
                if decoded_size > self._MAX_DECODED_BYTES:
                    raise ValueError("decoded WAV exceeds the 256 MiB safety limit")
                data = wav.readframes(frames)
        except (EOFError, wave.Error) as error:
            raise ValueError(f"invalid WAV file: {source}") from error
        if len(data) != decoded_size:
            raise ValueError("WAV ended before all declared sample frames were read")
        sound = Sound(
            self,
            self._engine.audio_create_pcm16_sound(data, channels, sample_rate),
            source,
            channels,
            sample_rate,
            frames,
        )
        self._sounds[source] = sound
        return sound

    def play(
        self,
        sound: Sound,
        *,
        volume: float = 1.0,
        loop: bool = False,
        position: Vec3 | tuple[float, float, float] | None = None,
        minimum_distance: float = 1.0,
        maximum_distance: float = 50.0,
    ) -> AudioSource:
        """Play a sound; supplying ``position`` enables camera-relative 3D audio."""

        if not isinstance(sound, Sound) or sound._audio is not self:
            raise ValueError("sound must have been loaded by this game's Audio manager")
        gain = _volume(volume)
        if isinstance(loop, bool) is False:
            raise TypeError("loop must be bool")
        source_position = Vec3() if position is None else Vec3.from_value(position)
        voice_id = self._engine.audio_play(
            sound._id,
            gain,
            loop,
            position is not None,
            tuple(source_position),
            minimum_distance,
            maximum_distance,
        )
        return AudioSource(
            self, voice_id, gain, source_position, position is not None, loop
        )

    @property
    def available(self) -> bool:
        """Whether a native playback device is active during the current run."""

        return self._engine.audio_backend_active

    @property
    def sound_count(self) -> int:
        return self._engine.audio_sound_count

    @property
    def active_voice_count(self) -> int:
        return self._engine.audio_active_voice_count
