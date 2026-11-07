"""Finite reconnect, spam, loss, and shutdown soak for RIX networking."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import struct
import time

from rix import Entity, Scene
from rix import net as network
from rix.net import NetworkError, Server
from rix.net import replication


PLAYER = 1
INPUT = 1
_ASSIGN = struct.Struct("<4sQ")
_ASSIGN_MAGIC = b"E3DA"


@dataclass(frozen=True, slots=True)
class SoakReport:
    clients: int
    cycles: int
    profile: str
    inputs_sent: int
    inputs_received: int
    inputs_executed: int
    inputs_rate_limited: int
    disconnects_observed: int
    reconnects_completed: int
    shutdown_disconnects_observed: int
    elapsed_seconds: float
    correct: bool


def _server(on_connect, on_disconnect, clients: int) -> Server:  # type: ignore[no-untyped-def]
    for port in range(33200, 33300):
        server = Server(
            port=port,
            max_players=clients,
            bind_address="127.0.0.1",
            handshake_timeout=5,
            peer_timeout=8,
            event_queue_capacity=max(4096, clients * 512),
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise RuntimeError("no loopback soak port is available")


def run_soak(
    client_count: int = 4,
    *,
    cycles: int = 10,
    inputs_per_client: int = 64,
    profile: network.NetworkCondition = network.ADVERSE_NETWORK_CONDITION,
) -> SoakReport:
    if isinstance(client_count, bool) or not isinstance(client_count, int):
        raise TypeError("client_count must be an integer")
    if not 2 <= client_count <= 32:
        raise ValueError("client_count must be in [2, 32]")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1:
        raise ValueError("cycles must be a positive integer")
    if (
        isinstance(inputs_per_client, bool)
        or not isinstance(inputs_per_client, int)
        or not 17 <= inputs_per_client <= 1000
    ):
        raise ValueError("inputs_per_client must be in [17, 1000]")
    if not isinstance(profile, network.NetworkCondition):
        raise TypeError("profile must be an rix.net.NetworkCondition")

    owner_box: list[replication.ServerReplication] = []
    players: dict[network.ConnectionId, replication.NetworkObjectId] = {}
    server_disconnects: list[network.NetworkEvent] = []
    executed_inputs = 0

    def input_handler(
        _entity: Entity, _connection: network.ConnectionId, _client_sequence: int
    ) -> None:
        nonlocal executed_inputs
        executed_inputs += 1

    registry = replication.PrefabRegistry(schema_version=17)
    registry.register(PLAYER, "soak_player", lambda scene: Entity("soak player", scene=scene))
    registry.register_rpc(
        PLAYER,
        INPUT,
        "submit_input",
        "client_to_server",
        (("int", 8),),
        input_handler,
        reliable=True,
        rate_limit=16,
        require_owner=True,
    )

    def connected(server: Server, connection: network.ConnectionId) -> None:
        owner = owner_box[0]
        player = owner.spawn(PLAYER)
        owner.set_owner(player.id, connection)
        players[connection] = player.id
        status = server.send(
            connection,
            _ASSIGN.pack(_ASSIGN_MAGIC, player.id.value),
            delivery=network.Delivery.RELIABLE,
        )
        if status is not network.SendStatus.QUEUED:
            server.disconnect(connection, "soak assignment backpressure")

    def disconnected(_server: Server, event: network.NetworkEvent) -> None:
        server_disconnects.append(event)
        identifier = players.pop(event.connection, None)
        owner = owner_box[0]
        if identifier is not None and any(item.id == identifier for item in owner.objects):
            owner.despawn(identifier)

    server = _server(connected, disconnected, client_count)
    server.load_scene(Scene("network soak authority"))
    owner = replication.ServerReplication(
        server,
        registry,
        max_objects=client_count + cycles + 8,
    )
    owner_box.append(owner)
    clients: list[network.Client] = []
    mirrors: list[replication.ClientReplication] = []
    assignments: list[replication.NetworkObjectId | None] = [None] * client_count
    shutdown_events: set[int] = set()
    shutdown_started = False

    def service() -> None:
        if server.state is network.ServerState.LISTENING:
            server.poll(maximum_events=16384)
        for index, mirror in enumerate(mirrors):
            for event in mirror.poll(maximum_events=8192):
                if event.type is network.EventType.MESSAGE and len(event.payload) == _ASSIGN.size:
                    magic, object_value = _ASSIGN.unpack(event.payload)
                    if magic == _ASSIGN_MAGIC:
                        assignments[index] = replication.NetworkObjectId(object_value)
                elif event.type is network.EventType.DISCONNECTED:
                    assignments[index] = None
                    # Under an impaired path the peer can observe the explicit
                    # close or liveness loss; both are valid shutdown outcomes.
                    if shutdown_started:
                        shutdown_events.add(index)

    def wait_for(predicate, label: str, timeout: float = 20.0) -> None:  # type: ignore[no-untyped-def]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            service()
            time.sleep(0.001)
        if not predicate():
            raise RuntimeError(f"network soak timed out waiting for {label}")

    started = time.perf_counter()
    total_sent = 0
    completed_reconnects = 0
    try:
        with network.impair_backend(profile):
            for index in range(client_count):
                client = network.Client(
                    timeout=6,
                    peer_timeout=8,
                    event_queue_capacity=max(2048, inputs_per_client * 4),
                )
                clients.append(client)
                mirrors.append(
                    replication.ClientReplication(
                        client,
                        Scene(f"network soak client {index}"),
                        registry,
                        max_objects=client_count + cycles + 8,
                    )
                )
                client.connect("127.0.0.1", server.port)
            wait_for(
                lambda: len(players) == client_count
                and all(mirror.is_synchronized for mirror in mirrors)
                and all(identifier is not None for identifier in assignments)
                and all(len(mirror.objects) == client_count for mirror in mirrors),
                "initial synchronization",
            )

            for cycle in range(cycles):
                target_received = owner.rpc_stats.received + (
                    client_count * inputs_per_client
                )
                for index, mirror in enumerate(mirrors):
                    identifier = assignments[index]
                    if identifier is None:
                        raise RuntimeError("soak client lost its assignment")
                    for input_index in range(inputs_per_client):
                        status = mirror.call_server(
                            identifier,
                            INPUT,
                            cycle * inputs_per_client + input_index + 1,
                        )
                        if status is not network.SendStatus.QUEUED:
                            raise RuntimeError("input spam encountered backpressure")
                        total_sent += 1
                wait_for(
                    lambda: owner.rpc_stats.received == target_received,
                    f"cycle {cycle} reliable input delivery",
                )

                target_index = cycle % client_count
                target_client = clients[target_index]
                target_client.disconnect(f"soak cycle {cycle}")
                wait_for(
                    lambda: target_client.connection is None
                    and len(players) == client_count - 1
                    and not mirrors[target_index].is_synchronized
                    and all(
                        len(mirror.objects) == client_count - 1
                        for index, mirror in enumerate(mirrors)
                        if index != target_index
                    ),
                    f"cycle {cycle} disconnect",
                )
                target_client.connect("127.0.0.1", server.port)
                wait_for(
                    lambda: target_client.state is network.ClientState.CONNECTED
                    and assignments[target_index] is not None
                    and len(players) == client_count
                    and mirrors[target_index].is_synchronized
                    and all(len(mirror.objects) == client_count for mirror in mirrors),
                    f"cycle {cycle} reconnect",
                )
                completed_reconnects += 1

        # Reset the process-global test impairment before the explicit stop.
        # Loss/retransmission was exercised above; a clean shutdown should
        # deterministically propagate its close rather than wait for timeout.
        shutdown_started = True
        server.stop("network soak shutdown")
        wait_for(
            lambda: len(shutdown_events) == client_count
            and all(client.connection is None for client in clients)
            and all(not mirror.is_synchronized for mirror in mirrors),
            "server shutdown propagation",
        )

        stats = owner.rpc_stats
        correct = (
            total_sent == stats.received
            and stats.executed == executed_inputs
            and stats.rate_limited > 0
            and completed_reconnects == cycles
            and len(shutdown_events) == client_count
            and len(server_disconnects) == cycles + client_count
            and not players
            and not owner.objects
        )
        return SoakReport(
            client_count,
            cycles,
            profile.name,
            total_sent,
            stats.received,
            stats.executed,
            stats.rate_limited,
            len(server_disconnects),
            completed_reconnects,
            len(shutdown_events),
            time.perf_counter() - started,
            correct,
        )
    finally:
        for mirror in mirrors:
            mirror.clear()
        for client in clients:
            if client.connection is not None:
                client.disconnect("soak cleanup")
                client.poll()
        owner.close(destroy=True)
        if server.state is network.ServerState.LISTENING:
            server.stop("soak cleanup")
        server.unload_scene(clear=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--inputs-per-client", type=int, default=64)
    parser.add_argument("--profile", choices=("lan", "regional", "adverse"), default="adverse")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    profile = {
        item.name: item for item in network.REPRESENTATIVE_NETWORK_CONDITIONS
    }[args.profile]
    report = run_soak(
        args.clients,
        cycles=args.cycles,
        inputs_per_client=args.inputs_per_client,
        profile=profile,
    )
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(
            f"clients={report.clients} cycles={report.cycles} profile={report.profile} "
            f"sent/received/executed/limited={report.inputs_sent}/"
            f"{report.inputs_received}/{report.inputs_executed}/"
            f"{report.inputs_rate_limited} disconnects={report.disconnects_observed} "
            f"reconnects={report.reconnects_completed} "
            f"shutdown_clients={report.shutdown_disconnects_observed} "
            f"elapsed={report.elapsed_seconds:.3f}s correct={report.correct}"
        )
    if not report.correct:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
