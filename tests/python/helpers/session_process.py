from __future__ import annotations

import argparse
import time

from rix import net


def run_server(port: int) -> None:
    session = net.Session()
    responded_at: float | None = None

    @session.on("ping")
    def ping(sender: net.Player, *, value: int) -> None:
        nonlocal responded_at
        session.send_to(sender, "pong", value=value)
        responded_at = time.monotonic()

    session.register_message("ping", value=int)
    session.register_message("pong", value=int)
    session.host(port=port, bind_address="127.0.0.1")
    print("READY", flush=True)
    deadline = time.monotonic() + 8.0
    try:
        while time.monotonic() < deadline:
            session.update()
            if responded_at is not None and time.monotonic() - responded_at >= 0.25:
                break
            time.sleep(0.001)
    finally:
        session.close()
    if responded_at is None:
        raise RuntimeError("server timed out")


def run_client(port: int) -> None:
    session = net.Session()
    reply: list[int] = []

    @session.on("pong")
    def pong(_sender: net.Player, *, value: int) -> None:
        reply.append(value)

    session.register_message("ping", value=int)
    session.register_message("pong", value=int)
    session.join(f"127.0.0.1:{port}")
    deadline = time.monotonic() + 8.0
    sent = False
    try:
        while not reply and time.monotonic() < deadline:
            session.update()
            if not sent and session.is_open:
                status = session.send("ping", value=42)
                sent = status is net.SendStatus.QUEUED
            time.sleep(0.001)
    finally:
        session.close()
    if reply != [42]:
        raise RuntimeError(f"unexpected reply: {reply!r}")
    print("PONG 42", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("server", "client"))
    parser.add_argument("port", type=int)
    args = parser.parse_args()
    (run_server if args.role == "server" else run_client)(args.port)


if __name__ == "__main__":
    main()
