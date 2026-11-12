"""Illustrates state-management pattern: 02 Enemy Conditions.

Run from the repository root with `python examples/states/02_enemy_conditions.py`. See
`examples/states/README.md` for the state-example index."""

from rix import StateMachine

enemy_distance = 20.0
states = StateMachine("patrol")


@states.state("patrol")
def patrol(_dt: float) -> None:
    print("patrolling")


@states.state("chase")
def chase(_dt: float) -> None:
    print("chasing")


states.when("patrol", "chase", condition=lambda: enemy_distance < 8, priority=10)
states.when("chase", "patrol", condition=lambda: enemy_distance >= 12)
states.update(0)
enemy_distance = 5
states.update(0)
