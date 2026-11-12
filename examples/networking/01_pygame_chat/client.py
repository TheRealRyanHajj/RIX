"""Client process for the adjacent RIX networking example.

Run from the repository root with `python examples/networking/01_pygame_chat/client.py`.
Check the nearby README for controls, assets, or multi-process startup instructions."""

from __future__ import annotations

import argparse

import pygame
from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description="Pygame-only RIX chat client")
    parser.add_argument("address", nargs="?", default="127.0.0.1:7777")
    args = parser.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((800, 500), pygame.RESIZABLE)
    pygame.display.set_caption("RIX Pygame chat")
    font = pygame.font.Font(None, 28)
    clock = pygame.time.Clock()
    session = net.Session()
    session.register_message("chat", text=str)
    lines = [f"Connecting to {args.address}"]
    typed = ""

    @session.on("connect")
    def connected(_server: net.Player) -> None:
        lines.append("Connected. Type a message and press Enter.")

    @session.on("disconnect")
    def disconnected(_server: net.Player, reason: str) -> None:
        lines.append(f"Disconnected: {reason}")

    @session.on("chat")
    def chat(_server: net.Player, *, text: str) -> None:
        lines.append(text)
        del lines[:-14]

    session.join(args.address)
    running = True
    try:
        while running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and typed:
                        session.send("chat", text=typed)
                        typed = ""
                    elif event.key == pygame.K_BACKSPACE:
                        typed = typed[:-1]
                    elif event.unicode.isprintable():
                        typed += event.unicode
            session.update(dt)
            screen.fill("#10151d")
            for index, line in enumerate(lines[-14:]):
                screen.blit(font.render(line, True, "#d9e2f2"), (20, 20 + index * 28))
            pygame.draw.rect(screen, "#273448", (14, screen.get_height() - 48, screen.get_width() - 28, 36))
            screen.blit(font.render("> " + typed, True, "white"), (20, screen.get_height() - 42))
            pygame.display.flip()
    finally:
        session.close()
        pygame.quit()


if __name__ == "__main__":
    main()
