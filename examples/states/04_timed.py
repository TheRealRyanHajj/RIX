"""Illustrates state-management pattern: 04 Timed.

Run from the repository root with `python examples/states/04_timed.py`. See
`examples/states/README.md` for the state-example index."""

from rix import StateMachine

states = StateMachine("countdown")


@states.state("countdown")
def countdown(_dt: float) -> None:
    print(f"starting in {max(0, 3 - int(states.elapsed))}")


@states.state("playing")
def playing(_dt: float) -> None:
    print("go!")


states.after(3.0, "playing", state="countdown")
for _ in range(4):
    states.update(1.0)
