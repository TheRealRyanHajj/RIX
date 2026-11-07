"""Discover compatible LAN hosts, then connect through the normal Session."""

from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default="255.255.255.255")
    parser.add_argument("--discovery-port", type=int, default=47777)
    args = parser.parse_args()
    browser = net.LanDiscoveryBrowser(discovery_port=args.discovery_port)
    try:
        browser.start()
        browser.refresh(args.target)
        deadline = time.monotonic() + 2.0
        found = None
        while time.monotonic() < deadline and found is None:
            results = browser.poll()
            found = next((server for server in results if server.compatible), None)
            time.sleep(0.01)
    finally:
        browser.close()
    if found is None:
        raise SystemExit("no compatible LAN server found")
    print(f"found {found.name} at {found.address}:{found.port}")

    session = net.Session()
    session.register_message("hello", text=str)

    @session.on("connect")
    def connected(_server: net.Player) -> None:
        session.send("hello", text="hello from discovered client")

    @session.on("hello")
    def hello(_server: net.Player, *, text: str) -> None:
        print(text)
        session.close("example complete")

    session.join(f"{found.address}:{found.port}")
    deadline = time.monotonic() + 3.0
    while session.is_open and time.monotonic() < deadline:
        session.update(0.01)
        time.sleep(0.01)
    session.close()


if __name__ == "__main__":
    main()
