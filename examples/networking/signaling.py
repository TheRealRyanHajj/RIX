"""Run or query the optional self-hosted RIX room-code directory."""

from __future__ import annotations

import argparse
import time

from rix import net


def _wait_connected(
    server: str, timeout: float
) -> tuple[net.SignalingClient, list[net.SignalingEvent]]:
    client = net.SignalingClient(timeout=timeout)
    client.connect(server)
    events: list[net.SignalingEvent] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(client.poll())
        if any(event.type is net.SignalingEventType.CONNECTED for event in events):
            return client, events
        if any(event.type is net.SignalingEventType.DISCONNECTED for event in events):
            break
        time.sleep(0.001)
    client.close()
    raise RuntimeError("signaling connection did not establish")


def _serve(args: argparse.Namespace) -> int:
    server = net.SignalingServer(port=args.port, bind_address=args.bind)
    server.start()
    print(f"signaling directory listening on {server.bind_address}", flush=True)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop("operator stopped signaling directory")
    return 0


def _register(args: argparse.Namespace) -> int:
    client, events = _wait_connected(args.server, args.timeout)
    try:
        status = client.register(args.room, args.endpoint)
        if status is not net.SendStatus.QUEUED:
            raise RuntimeError(f"registration send failed: {status.value}")
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            events.extend(client.poll())
            for event in events:
                if event.type is net.SignalingEventType.REGISTERED:
                    assert event.endpoint is not None
                    print(
                        f"room {event.room_code} -> "
                        f"{event.endpoint.connection_string}",
                        flush=True,
                    )
                    print("keep this process open; Ctrl+C releases the room")
                    try:
                        while True:
                            for update in client.poll():
                                if update.type is net.SignalingEventType.DISCONNECTED:
                                    return 2
                            time.sleep(0.01)
                    except KeyboardInterrupt:
                        return 0
                if event.type is net.SignalingEventType.ERROR:
                    raise RuntimeError(event.reason)
            time.sleep(0.001)
        raise RuntimeError("room registration timed out")
    finally:
        client.close()


def _resolve(args: argparse.Namespace) -> int:
    client, events = _wait_connected(args.server, args.timeout)
    try:
        status = client.resolve(args.room)
        if status is not net.SendStatus.QUEUED:
            raise RuntimeError(f"resolve send failed: {status.value}")
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            events.extend(client.poll())
            for event in events:
                if event.type is net.SignalingEventType.RESOLVED:
                    assert event.endpoint is not None
                    print(event.endpoint.connection_string)
                    return 0
                if event.type is net.SignalingEventType.NOT_FOUND:
                    print(f"room {event.room_code} was not found")
                    return 3
                if event.type is net.SignalingEventType.ERROR:
                    raise RuntimeError(event.reason)
            time.sleep(0.001)
        raise RuntimeError("room resolution timed out")
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    roles = parser.add_subparsers(dest="role", required=True)
    serve = roles.add_parser("serve", help="run the headless directory")
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7790)

    register = roles.add_parser("register", help="hold one room registration")
    register.add_argument("room")
    register.add_argument("endpoint", help="numeric game endpoint, including port")
    register.add_argument("--server", default="127.0.0.1:7790")
    register.add_argument("--timeout", type=float, default=5.0)

    resolve = roles.add_parser("resolve", help="resolve one room and exit")
    resolve.add_argument("room")
    resolve.add_argument("--server", default="127.0.0.1:7790")
    resolve.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    try:
        if args.role == "serve":
            return _serve(args)
        if args.role == "register":
            return _register(args)
        return _resolve(args)
    except (net.NetworkError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
