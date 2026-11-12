"""Contextual retained UI layout with reactive text."""

# Usage: from the repository root, run:
#   python examples/beginner/08_hud_menu.py

from rix import Button, Game, Panel, Row, Text


game = Game("HUD and Menu")
status = Text("Choose an action", x=20, y=20)
Panel(anchor="bottom", width=520, height=90, color="#111827dd")
with Row(anchor="bottom", gap=16, padding=18):
    Button("Play", click=lambda: setattr(status, "text", "Playing!"))
    Button("Quit", click=game.stop)
game.run()
