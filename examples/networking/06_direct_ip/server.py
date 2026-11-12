"""Direct-IP Session host; expose the UDP port only when deployment is secured."""

# Usage: from the repository root, run:
#   python examples/networking/06_direct_ip/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7782)
    args = parser.parse_args()
    session = net.Session()
    session.register_message("echo", text=str)

    @session.on("echo")
    def echo(sender: net.Player, *, text: str) -> None:
        session.send_to(sender, "echo", text=text)

    try:
        session.host(port=args.port, bind_address=args.bind)
        print(f"direct-IP host on {args.bind}:{args.port}; Ctrl+C stops it")
        while True:
            session.update(0.01)
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        session.close()


if __name__ == "__main__":
    main()
