from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless RIX chat server")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()

    session = net.Session()
    session.register_message("chat", text=str)

    @session.on("connect")
    def joined(player: net.Player) -> None:
        print(f"connected: {player.id} local={player.local}")

    @session.on("disconnect")
    def left(player: net.Player, reason: str) -> None:
        print(f"disconnected: {player.id}: {reason}")

    @session.on("chat")
    def chat(sender: net.Player, *, text: str) -> None:
        # Broadcasts arrive at the host's isolated local client with SERVER as
        # sender; ignore that copy so it is not broadcast recursively.
        if sender.server:
            return
        print(f"{sender.id}: {text}")
        session.broadcast("chat", text=f"{sender.id}: {text}")

    session.host(port=args.port)
    print(f"chat server listening on UDP {args.port}; Ctrl+C stops it")
    try:
        while True:
            session.update()
            time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        session.close()


if __name__ == "__main__":
    main()
