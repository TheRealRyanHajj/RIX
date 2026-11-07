"""Two independent Pygame processes playing authoritative Tic-Tac-Toe."""

from __future__ import annotations

import argparse
import math

import pygame

from rix import net


LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def winner(cells: list[str]) -> str:
    for first, second, third in LINES:
        if cells[first] and cells[first] == cells[second] == cells[third]:
            return cells[first]
    return ""


def configure(session: net.Session) -> None:
    session.register_message("assign", mark=str, player=int)
    session.register_message("move", cell=int)
    session.register_message(
        "state", cells=list, turn=int, winner=str, draw=bool
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true", help="host and play as X")
    parser.add_argument("--address", default="127.0.0.1:7777")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((600, 680), pygame.RESIZABLE)
    pygame.display.set_caption("RIX Tic-Tac-Toe")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 88)
    small = pygame.font.Font(None, 34)
    session = net.Session()
    configure(session)

    cells = [""] * 9
    player_id = -1
    mark = ""
    turn = -1
    result = ""
    draw = False
    players: list[int] = []

    def publish() -> None:
        if session.role is net.SessionRole.HOST:
            session.broadcast(
                "state",
                cells=list(cells),
                turn=turn,
                winner=result,
                draw=draw,
            )

    @session.on("connect")
    def connected(player: net.Player) -> None:
        nonlocal turn
        if not args.host or player.server:
            return
        if player.id not in players and len(players) < 2:
            players.append(player.id)
        if player.id in players:
            session.send_to(
                player,
                "assign",
                mark="X" if players.index(player.id) == 0 else "O",
                player=player.id,
            )
        if len(players) == 2 and turn < 0:
            turn = players[0]
        publish()

    @session.on("disconnect")
    def disconnected(player: net.Player, _reason: str) -> None:
        nonlocal turn
        if args.host and player.id in players:
            players.remove(player.id)
            turn = players[0] if len(players) == 2 else -1
            publish()

    @session.on("assign")
    def assigned(_sender: net.Player, *, mark: str, player: int) -> None:
        nonlocal player_id
        globals_marker[0] = mark
        player_id = player

    @session.on("state")
    def state(
        _sender: net.Player,
        *,
        cells: list[object],
        turn: int,
        winner: str,
        draw: bool,
    ) -> None:
        if len(cells) == 9 and all(value in ("", "X", "O") for value in cells):
            board[:] = [str(value) for value in cells]
            state_values[:] = [turn, winner, draw]

    @session.on("move")
    def move(sender: net.Player, *, cell: int) -> None:
        nonlocal turn, result, draw
        if not args.host or sender.id != turn or result or draw:
            return
        if not 0 <= cell < 9 or cells[cell] or sender.id not in players:
            return
        cells[cell] = "X" if players.index(sender.id) == 0 else "O"
        result = winner(cells)
        draw = not result and all(cells)
        if not result and not draw:
            turn = players[1 - players.index(sender.id)]
        publish()

    # Mutable callback-visible client presentation holders.
    board = cells if args.host else [""] * 9
    globals_marker = [mark]
    state_values: list[object] = [turn, result, draw]

    try:
        if args.host:
            session.host(port=7777, max_players=2, bind_address="0.0.0.0")
        else:
            session.join(args.address)

        running = True
        while running and session.is_open:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    width = min(screen.get_width(), screen.get_height() - 80)
                    left = (screen.get_width() - width) // 2
                    x, y = event.pos
                    if left <= x < left + width and 0 <= y < width:
                        column = int((x - left) * 3 / width)
                        row = int(y * 3 / width)
                        session.send("move", cell=row * 3 + column)

            session.update(dt)
            mark = globals_marker[0]
            turn = int(state_values[0])
            result = str(state_values[1])
            draw = bool(state_values[2])
            width = min(screen.get_width(), screen.get_height() - 80)
            left = (screen.get_width() - width) // 2
            screen.fill("#111827")
            for index in (1, 2):
                offset = index * width // 3
                pygame.draw.line(screen, "#94a3b8", (left + offset, 0), (left + offset, width), 4)
                pygame.draw.line(screen, "#94a3b8", (left, offset), (left + width, offset), 4)
            for index, value in enumerate(board):
                if value:
                    glyph = font.render(value, True, "#f59e0b" if value == "X" else "#38bdf8")
                    center = (
                        left + (index % 3) * width // 3 + width // 6,
                        (index // 3) * width // 3 + width // 6,
                    )
                    screen.blit(glyph, glyph.get_rect(center=center))
            status = (
                f"Winner: {result}"
                if result
                else "Draw"
                if draw
                else "Your turn"
                if player_id == turn
                else "Waiting for opponent"
                if turn < 0
                else "Opponent's turn"
            )
            label = small.render(f"You are {mark or '?'} — {status}", True, "white")
            screen.blit(label, (20, width + 24))
            pygame.display.flip()
    finally:
        session.close()
        pygame.quit()


if __name__ == "__main__":
    main()
