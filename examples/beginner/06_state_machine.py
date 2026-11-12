"""A small explicit state machine driven by ordinary game callbacks."""

# Usage: from the repository root, run:
#   python examples/beginner/06_state_machine.py

from rix import Cube, Game, StateMachine, Text


game = Game("State Machine")
actor = Cube(color="yellow")
status = Text("State: idle", x=20, y=20)
machine = StateMachine()
machine.add_state("idle", on_enter=lambda _old: setattr(status, "text", "IDLE"))
machine.add_state("moving", on_enter=lambda _old: setattr(status, "text", "MOVING"))
machine.add_transition("idle", "moving", "toggle")
machine.add_transition("moving", "idle", "toggle")
machine.start("idle")


@game.on_key("space")
def toggle() -> None:
    machine.trigger("toggle")


@game.update
def update(dt: float) -> None:
    machine.update(dt)
    if machine.current == "moving":
        actor.rotate((0, 90 * dt, 0))


game.run()
