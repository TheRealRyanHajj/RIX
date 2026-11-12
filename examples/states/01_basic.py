"""Illustrates state-management pattern: 01 Basic.

Run from the repository root with `python examples/states/01_basic.py`. See
`examples/states/README.md` for the state-example index."""

from rix import StateMachine

moving = False
states = StateMachine("idle")


@states.state("idle")
def idle(_dt: float) -> None:
    print("idle")
    if moving:
        states.change("run")


@states.state("run")
def run(_dt: float) -> None:
    print("running")


states.update(1 / 60)
moving = True
states.update(1 / 60)
states.update(1 / 60)
