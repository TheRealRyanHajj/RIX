# Playing Sounds

Play an uncompressed 16-bit PCM WAV in one call:

```python
source = game.play_sound("assets/jump.wav", volume=0.8)
```

Passing a position enables positional attenuation:

```python
game.play_sound(
    "assets/explosion.wav",
    volume=0.8,
    position=enemy.position,
)
```

Repeated calls reuse the game-local decoded sound cache. Use `game.audio.load`
and `game.audio.play` when you want explicit `Sound` reuse, looping, distance
limits, live volume/position changes, or a playback handle.
