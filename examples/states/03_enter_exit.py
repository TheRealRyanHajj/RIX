from rix import StateMachine

states = StateMachine("closed")


@states.state("closed")
def closed(_dt: float) -> None:
    pass


@states.state("open")
def opened(_dt: float) -> None:
    pass


@states.exit("closed")
def unlock(target: str | None) -> None:
    print("unlocking for", target)


@states.enter("open")
def play_sound(previous: str | None) -> None:
    print("opened from", previous)


states.update(0)
states.change("open")
