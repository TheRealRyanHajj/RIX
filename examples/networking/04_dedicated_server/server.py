"""Independent headless authoritative echo server using safe message frames."""

# Usage: from the repository root, run:
#   python examples/networking/04_dedicated_server/server.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7780)
    args = parser.parse_args()

    def connected(_server: net.Server, connection: net.ConnectionId) -> None:
        print("connected", connection.value)

    def message(server: net.Server, event: net.NetworkEvent) -> None:
        try:
            incoming = net.decode_message(event.payload)
            if incoming.name != "ping" or set(incoming.fields) != {"sequence"}:
                raise ValueError("expected ping(sequence=int)")
            sequence = incoming.fields["sequence"]
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise ValueError("sequence must be int")
        except (TypeError, ValueError) as error:
            server.disconnect(event.connection, f"invalid message: {error}")
            return
        server.send(
            event.connection,
            net.encode_message("pong", {"sequence": sequence}),
        )

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        print("disconnected", event.connection.value, event.reason)

    server = net.Server(
        bind_address=args.bind,
        port=args.port,
        tick_rate=60,
        on_connect=connected,
        on_message=message,
        on_disconnect=disconnected,
    )
    print(f"headless server on {args.bind}:{args.port}; Ctrl+C stops it")
    try:
        server.run()
    except KeyboardInterrupt:
        server.stop("operator interrupted")


if __name__ == "__main__":
    main()
