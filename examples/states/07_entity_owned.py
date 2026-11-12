"""Illustrates state-management pattern: 07 Entity Owned.

Run from the repository root with `python examples/states/07_entity_owned.py`. See
`examples/states/README.md` for the state-example index."""

from rix import Entity, Game

game = Game("Entity-owned states")
actor = Entity("Actor")
states = actor.state_machine("idle")


@states.state("idle")
def idle(_dt: float) -> None:
    actor.ry += 1


game.after(3.0, game.stop)
game.run()
