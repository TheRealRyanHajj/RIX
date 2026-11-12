"""Illustrates state-management pattern: 10 Animation Selection.

Run from the repository root with `python examples/states/10_animation_selection.py`.
See `examples/states/README.md` for the state-example index."""

from rix import AnimationSelection, StateMachine

# RIX currently exposes clip-selection intent and glTF sampling metadata; the
# renderer still draws imported models in their base pose (no skinned claim).
animations = AnimationSelection()
states = StateMachine("idle")
states.bind_animations(animations)


@states.state("idle", animation="idle")
def idle(_dt: float) -> None:
    pass


@states.state("run", animation="run")
def run(_dt: float) -> None:
    pass


states.update(0)
print(animations.current, animations.revision)
states.change("run")
print(animations.current, animations.revision)
animations.play("run")               # no restart
animations.play("run", restart=True) # explicit restart intent
