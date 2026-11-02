"""Two-process direct-IP Easy3D transport sample."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time

from easy3d import NetworkError, Server, network


REQUEST = b"easy3d phase 3 ping"
RESPONSE = b"easy3d phase 3 pong"


def _marker(path: str | None, text: str) -> None:
    if path is not None:
        Path(path).write_text(text + "\n", encoding="utf-8")


def _server(arguments: argparse.Namespace) -> int:
    had_connection = False
    exchange_complete = False
    invalid_message = False

    def connected(_server: Server, connection: network.ConnectionId) -> None:
        nonlocal had_connection
        had_connection = True
        _marker(arguments.connection_file, str(connection.value))
        print(f"SERVER_CONNECTED id={connection.value}", flush=True)

    def received(server: Server, event: network.NetworkEvent) -> None:
        nonlocal exchange_complete, invalid_message
        if event.payload != REQUEST:
            invalid_message = True
            print("SERVER_INVALID_MESSAGE", flush=True)
            return
        status = server.send(event.connection, RESPONSE)
        if status is not network.SendStatus.QUEUED:
            invalid_message = True
            print(f"SERVER_SEND_FAILED status={status.value}", flush=True)
            return
        exchange_complete = True
        print("SERVER_RECEIVED request=ping", flush=True)

    def disconnected(_server: Server, event: network.NetworkEvent) -> None:
        print(
            f"SERVER_DISCONNECTED id={event.connection.value} "
            f"code={event.disconnect_code}",
            flush=True,
        )

    server = Server(
        bind_address=arguments.bind,
        port=arguments.port,
        handshake_timeout=min(arguments.timeout, 5.0),
        peer_timeout=arguments.peer_timeout,
        on_connect=connected,
        on_message=received,
        on_disconnect=disconnected,
    )
    try:
        server.start()
    except (NetworkError, ValueError) as error:
        print(f"SERVER_START_FAILED {error}", file=sys.stderr, flush=True)
        return 2

    _marker(arguments.ready_file, f"{arguments.bind}:{server.port}")
    print(
        f"SERVER_READY address={arguments.bind} port={server.port}",
        flush=True,
    )
    deadline = time.monotonic() + arguments.timeout
    result = 0
    try:
        while time.monotonic() < deadline:
            server.poll()
            if invalid_message:
                result = 3
                break
            if arguments.one_shot and had_connection and not server.connections:
                if exchange_complete:
                    print("SERVER_DONE exchange=complete", flush=True)
                    break
                print("SERVER_PEER_LOST exchange=incomplete", flush=True)
                result = 4
                break
            time.sleep(0.001)
        else:
            print("SERVER_TIMEOUT", file=sys.stderr, flush=True)
            result = 5
    except KeyboardInterrupt:
        print("SERVER_INTERRUPTED", flush=True)
        result = 0
    finally:
        if server.state is network.ServerState.LISTENING:
            server.stop("two-process sample stopped")
    return result


def _client(arguments: argparse.Namespace) -> int:
    client = network.Client(
        timeout=min(arguments.timeout, 5.0),
        peer_timeout=arguments.peer_timeout,
    )
    try:
        client.connect(arguments.address, arguments.port)
    except (NetworkError, ValueError) as error:
        print(f"CLIENT_START_FAILED {error}", file=sys.stderr, flush=True)
        return 2

    connected = False
    sent = False
    deadline = time.monotonic() + arguments.timeout
    hold_deadline = float("inf")
    while time.monotonic() < deadline:
        for event in client.poll():
            if event.type is network.EventType.CONNECTED:
                connected = True
                hold_deadline = time.monotonic() + arguments.hold_after_connect
                _marker(
                    arguments.ready_file,
                    f"{arguments.address}:{arguments.port}",
                )
                print(f"CLIENT_CONNECTED id={event.connection.value}", flush=True)
            elif event.type is network.EventType.MESSAGE:
                if event.payload != RESPONSE:
                    print("CLIENT_INVALID_RESPONSE", file=sys.stderr, flush=True)
                    return 3
                print("CLIENT_RECEIVED response=pong", flush=True)
                client.disconnect("two-process sample complete")
            elif event.type is network.EventType.DISCONNECTED:
                print(
                    f"CLIENT_DISCONNECTED code={event.disconnect_code} "
                    f"reason={event.reason!r}",
                    flush=True,
                )
                if arguments.expect_disconnect and connected:
                    print("CLIENT_DONE abrupt_disconnect=observed", flush=True)
                    return 0
                if sent and event.disconnect_code == int(network.DisconnectCode.NORMAL):
                    print("CLIENT_DONE exchange=complete", flush=True)
                    return 0
                return 4

        if (
            connected
            and not sent
            and not arguments.expect_disconnect
            and time.monotonic() >= hold_deadline
        ):
            status = client.send(REQUEST)
            if status is not network.SendStatus.QUEUED:
                print(
                    f"CLIENT_SEND_FAILED status={status.value}",
                    file=sys.stderr,
                    flush=True,
                )
                return 5
            sent = True
            print("CLIENT_SENT request=ping", flush=True)
        time.sleep(0.001)

    print("CLIENT_TIMEOUT", file=sys.stderr, flush=True)
    return 6


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Easy3D two-process direct-IP transport sample"
    )
    roles = parser.add_subparsers(dest="role", required=True)

    server = roles.add_parser("server", help="run the authoritative listener")
    server.add_argument("--bind", default="0.0.0.0", help="numeric bind address")
    server.add_argument("--port", type=int, default=7777)
    server.add_argument("--timeout", type=float, default=60.0)
    server.add_argument("--peer-timeout", type=float, default=10.0)
    server.add_argument("--one-shot", action="store_true")
    server.add_argument("--ready-file", help=argparse.SUPPRESS)
    server.add_argument("--connection-file", help=argparse.SUPPRESS)

    client = roles.add_parser("client", help="connect to a numeric server address")
    client.add_argument("--address", default="127.0.0.1")
    client.add_argument("--port", type=int, default=7777)
    client.add_argument("--timeout", type=float, default=15.0)
    client.add_argument("--peer-timeout", type=float, default=10.0)
    client.add_argument("--hold-after-connect", type=float, default=0.0)
    client.add_argument("--expect-disconnect", action="store_true")
    client.add_argument("--ready-file", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if not math.isfinite(arguments.timeout) or arguments.timeout <= 0:
        print("timeout must be finite and positive", file=sys.stderr)
        return 64
    if (
        not math.isfinite(arguments.peer_timeout)
        or not 0.001 <= arguments.peer_timeout <= 2_147_483.647
    ):
        print("peer-timeout is outside its supported range", file=sys.stderr)
        return 64
    if arguments.role == "client" and (
        not math.isfinite(arguments.hold_after_connect)
        or arguments.hold_after_connect < 0
    ):
        print("hold-after-connect must be non-negative", file=sys.stderr)
        return 64
    if arguments.role == "server":
        return _server(arguments)
    return _client(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
