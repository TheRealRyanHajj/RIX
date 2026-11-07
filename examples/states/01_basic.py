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
