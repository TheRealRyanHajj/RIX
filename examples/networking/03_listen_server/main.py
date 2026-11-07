"""Finite real listen server with isolated authority and local client roles."""

from __future__ import annotations

import argparse
import time

from rix import net


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7779)
    parser.add_argument("--ticks", type=int, default=20)
    args = parser.parse_args()
    events: list[net.ListenEvent] = []

    def received(_host: net.ListenServer, event: net.ListenEvent) -> None:
        events.append(event)
        print(
            event.role.value,
            "local" if event.local_host else "remote",
            event.event.type.value,
            event.event.payload,
        )

    host = net.ListenServer(
        bind_address="127.0.0.1",
        port=args.port,
        tick_rate=60,
        on_event=received,
    )
    try:
        host.start()
        for tick in range(args.ticks):
            if tick == 2:
                host.client.send(b"local player input")
            host.step()
            if tick == 5 and host.authority_connection is not None:
                host.authority.send(
                    host.authority_connection,
                    b"authoritative reply",
                )
            time.sleep(1 / 120)
    finally:
        host.stop("example complete")
    print(f"completed {args.ticks} authoritative ticks and {len(events)} events")


if __name__ == "__main__":
    main()
