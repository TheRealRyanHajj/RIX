"""Advertise a real Session host on opt-in IPv4 LAN discovery."""

# Usage: from the repository root, run:
#   python examples/networking/05_lan_discovery/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7781)
    parser.add_argument("--discovery-port", type=int, default=47777)
    args = parser.parse_args()
    session = net.Session()
    session.register_message("hello", text=str)

    @session.on("hello")
    def hello(sender: net.Player, *, text: str) -> None:
        print(sender.id, text)
        session.send_to(sender, "hello", text="LAN server received your message")

    announcer = net.LanDiscoveryAnnouncer(
        "RIX LAN example",
        args.port,
        discovery_port=args.discovery_port,
    )
    try:
        session.host(port=args.port, max_players=8)
        announcer.start()
        print("advertising; Ctrl+C stops it")
        while True:
            announcer.poll()
            session.update(0.01)
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        announcer.close()
        session.close()


if __name__ == "__main__":
    main()
