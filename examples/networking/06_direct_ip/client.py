"""Connect to an explicitly reachable numeric direct-IP address."""

from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", nargs="?", default="127.0.0.1:7782")
    args = parser.parse_args()
    session = net.Session()
    session.register_message("echo", text=str)

    @session.on("connect")
    def connected(_server: net.Player) -> None:
        session.send("echo", text="direct-IP round trip")

    @session.on("echo")
    def echoed(_server: net.Player, *, text: str) -> None:
        print(text)
        session.close("round trip complete")

    session.join(args.address)
    deadline = time.monotonic() + 5.0
    while session.is_open and time.monotonic() < deadline:
        session.update(0.01)
        time.sleep(0.01)
    session.close()


if __name__ == "__main__":
    main()
