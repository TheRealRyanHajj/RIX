from __future__ import annotations

import time

import pytest

from easy3d import Entity, NetworkError, Scene, Server, network


def _started_server(**arguments: object) -> Server:
    for port in range(32300, 32400):
        server = Server(
            port=port,
            bind_address="127.0.0.1",
            **arguments,  # type: ignore[arg-type]
        )
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise AssertionError("could not bind a localhost Python server test port")


def test_server_configuration_validation() -> None:
    for arguments in (
        {"port": 0},
        {"max_players": 0},
        {"max_players": 1025},
        {"tick_rate": 0},
        {"bind_address": ""},
        {"handshake_timeout": float("inf")},
        {"peer_timeout": 0},
        {"peer_timeout": float("inf")},
        {"event_queue_capacity": 0},
        {"maximum_message_size": 1024 * 1024 + 1},
        {"protocol_version": True},
        {"on_message": 42},
    ):
        with pytest.raises((TypeError, ValueError)):
            Server(**arguments)  # type: ignore[arg-type]
    invalid_address = Server(port=32399, bind_address="localhost")
    with pytest.raises(ValueError, match="numeric"):
        invalid_address.start()


def test_server_step_runs_scene_logic_and_physics_without_game() -> None:
    server = _started_server(tick_rate=120)
    scene = Scene("authoritative")

    class ServerLogic(Entity):
        def __init__(self) -> None:
            self.fixed_ticks = 0
            self.updates = 0
            super().__init__("logic", scene=scene)

        def fixed_update(self, dt: float) -> None:
            assert dt == pytest.approx(1 / 120)
            self.fixed_ticks += 1

        def update(self, dt: float) -> None:
            assert dt == pytest.approx(1 / 120)
            self.updates += 1

    logic = ServerLogic()
    scene.gravity = (0, -9.81, 0)
    server.load_scene(scene)
    try:
        assert "Engine" not in vars(network)
        assert server.state is network.ServerState.LISTENING
        assert server.connections == ()
        assert server.step() == ()
        assert server.step() == ()
        assert server.step() == ()
        assert logic.fixed_ticks == 3
        assert logic.updates == 3
        assert scene.physics_step_count == 3
        assert server.tick_count == 3
        assert server.scheduler_stats.fixed_ticks == 3
    finally:
        server.stop()
        assert server.unload_scene(clear=True) is scene


def test_server_run_is_paced_and_can_stop_from_python_logic() -> None:
    server = _started_server(tick_rate=200)
    scene = Scene("paced")

    class StopLogic(Entity):
        def __init__(self) -> None:
            self.fixed_ticks = 0
            super().__init__("stop logic", scene=scene)

        def fixed_update(self, _dt: float) -> None:
            self.fixed_ticks += 1
            if self.fixed_ticks == 4:
                server.stop("logic complete")

    logic = StopLogic()
    server.load_scene(scene)
    started = time.perf_counter()
    server.run()
    elapsed = time.perf_counter() - started
    assert logic.fixed_ticks == 4
    assert server.tick_count == 4
    assert elapsed >= 0.010
    assert elapsed < 1.0
    assert server.state is network.ServerState.STOPPED
    assert not server.is_running
    assert server.unload_scene(clear=True) is scene


def test_server_and_client_exchange_messages_and_callbacks() -> None:
    connected: list[network.ConnectionId] = []
    disconnected: list[network.NetworkEvent] = []
    received: list[network.NetworkEvent] = []

    def on_message(server: Server, event: network.NetworkEvent) -> None:
        received.append(event)
        assert server.send(
            event.connection, event.payload, delivery=event.delivery
        ) is network.SendStatus.QUEUED

    server = _started_server(
        on_connect=lambda _server, connection: connected.append(connection),
        on_disconnect=lambda _server, event: disconnected.append(event),
        on_message=on_message,
    )
    client = network.Client(timeout=1.0)
    try:
        client.connect("127.0.0.1", server.port)
        client_events: list[network.NetworkEvent] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not connected:
            server.poll()
            client_events.extend(client.poll())
            time.sleep(0.001)
        assert len(connected) == 1
        assert server.connections == (connected[0],)
        assert [event.type for event in client_events] == [
            network.EventType.CONNECTED
        ]

        assert client.send(
            b"authoritative echo", delivery=network.Delivery.UNRELIABLE
        ) is network.SendStatus.QUEUED
        echoed: list[network.NetworkEvent] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not echoed:
            server.poll()
            echoed.extend(
                event
                for event in client.poll()
                if event.type is network.EventType.MESSAGE
            )
            time.sleep(0.001)
        assert len(received) == 1
        assert received[0].payload == b"authoritative echo"
        assert received[0].delivery is network.Delivery.UNRELIABLE
        assert len(echoed) == 1
        assert echoed[0].payload == b"authoritative echo"
        assert echoed[0].delivery is network.Delivery.UNRELIABLE
        assert server.stats.messages_received == 1
        assert server.stats.messages_sent == 1

        server.stop("test complete")
        assert len(disconnected) == 1
        assert disconnected[0].disconnect_code is network.DisconnectCode.SERVER_STOPPED
        remote: list[network.NetworkEvent] = []
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not remote:
            remote.extend(client.poll())
            time.sleep(0.001)
        assert len(remote) == 1
        assert remote[0].type is network.EventType.DISCONNECTED
        assert remote[0].disconnect_code is network.DisconnectCode.SERVER_STOPPED
    finally:
        if server.state is network.ServerState.LISTENING:
            server.stop()
