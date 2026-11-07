from __future__ import annotations

import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import time

import rix
from rix import net


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples" / "networking"
REQUIRED = (
    "00_tic_tac_toe",
    "01_pygame_chat",
    "02_shared_state",
    "03_listen_server",
    "04_dedicated_server",
    "05_lan_discovery",
    "06_direct_ip",
    "07_synchronized_cubes",
    "08_cooperative_3d",
    "09_authoritative_fps",
    "10_health_scoring",
    "11_prediction_interpolation",
    "12_network_conditions",
)


def _unused_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_required_network_examples_are_documented_and_compile() -> None:
    directories = tuple(
        path.name
        for path in sorted(EXAMPLES.iterdir())
        if path.is_dir() and not path.name.startswith("__")
    )
    assert directories == REQUIRED
    index = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    for name in REQUIRED:
        directory = EXAMPLES / name
        assert (directory / "README.md").is_file()
        assert name in index
        sources = tuple(sorted(directory.glob("*.py")))
        assert sources
        for source in sources:
            compile(
                source.read_text(encoding="utf-8"),
                str(source),
                "exec",
            )


def test_network_condition_example_is_finite_and_repeatable() -> None:
    sample = EXAMPLES / "12_network_conditions" / "main.py"
    command = [
        sys.executable,
        "-u",
        str(sample),
        "--messages",
        "200",
        "--seed",
        "53",
    ]
    first = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    second = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout == second.stdout
    assert "lan      sent=200 delivered=200 lost=0" in first.stdout
    assert "regional sent=200 delivered=199 lost=1" in first.stdout
    assert "adverse  sent=200 delivered=194 lost=6" in first.stdout
    assert first.stderr == ""


def test_listen_server_example_exchanges_both_directions() -> None:
    sample = EXAMPLES / "03_listen_server" / "main.py"
    result = subprocess.run(
        [
            sys.executable,
            "-u",
            str(sample),
            "--port",
            str(_unused_udp_port()),
            "--ticks",
            "20",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "authority local message b'local player input'" in result.stdout
    assert "client local message b'authoritative reply'" in result.stdout
    assert "completed 20 authoritative ticks" in result.stdout
    assert result.stderr == ""


def test_authoritative_fps_keeps_remaining_clients_local_player() -> None:
    schema_path = EXAMPLES / "09_authoritative_fps" / "schema.py"
    spec = importlib.util.spec_from_file_location("rix_fps_example_schema", schema_path)
    assert spec is not None and spec.loader is not None
    schema = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schema)

    owner_box: list[net.ServerReplication] = []
    players: dict[net.ConnectionId, net.NetworkObjectId] = {}
    disconnects: list[tuple[net.ConnectionId, str]] = []

    def connected(_server: net.Server, connection: net.ConnectionId) -> None:
        player = owner_box[0].spawn(schema.PLAYER)
        owner_box[0].set_owner(player.id, connection)
        players[connection] = player.id
        assert owner_box[0].call_client(
            connection, player.id, schema.ASSIGNED, player.id.value
        ) is net.SendStatus.QUEUED

    def disconnected(_server: net.Server, event: net.NetworkEvent) -> None:
        disconnects.append((event.connection, event.reason))
        identifier = players.pop(event.connection, None)
        if identifier is not None and any(
            item.id == identifier for item in owner_box[0].objects
        ):
            owner_box[0].despawn(identifier)

    server = net.Server(
        port=_unused_udp_port(),
        bind_address="127.0.0.1",
        peer_timeout=2,
        on_connect=connected,
        on_disconnect=disconnected,
    )
    authority_scene = rix.Scene("FPS example authority")
    server.load_scene(authority_scene)
    owner = net.ServerReplication(server, schema.registry())
    owner_box.append(owner)
    server.start()
    clients = (net.Client(timeout=1, peer_timeout=2), net.Client(timeout=1, peer_timeout=2))
    scenes = (rix.Scene("FPS first"), rix.Scene("FPS second"))
    mirrors = tuple(
        net.ClientReplication(client, scene, schema.registry())
        for client, scene in zip(clients, scenes, strict=True)
    )

    def pump(predicate, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not predicate():
            server.poll()
            for mirror in mirrors:
                mirror.poll()
            time.sleep(0.001)
        assert predicate(), (
            len(server.connections),
            tuple(len(mirror.objects) for mirror in mirrors),
            tuple(client.state for client in clients),
            disconnects,
        )

    try:
        for client in clients:
            client.connect("127.0.0.1", server.port)
        pump(
            lambda: all(mirror.is_synchronized for mirror in mirrors)
            and all(
                any(hasattr(item.entity, "network_local_id") for item in mirror.objects)
                for mirror in mirrors
            )
        )
        second_local_id = next(
            int(item.entity.network_local_id)
            for item in mirrors[1].objects
            if hasattr(item.entity, "network_local_id")
        )
        clients[0].disconnect("example peer left")
        pump(lambda: len(server.connections) == 1 and len(mirrors[1].objects) == 1)
        assert any(
            item.id.value == second_local_id
            and getattr(item.entity, "network_local_id", None) == second_local_id
            for item in mirrors[1].objects
        )
    finally:
        for mirror in mirrors:
            mirror.clear()
        for client in clients:
            if client.connection is not None:
                client.disconnect("test cleanup")
                client.poll()
        owner.close(destroy=True)
        server.stop("test cleanup")
        server.unload_scene(clear=True)
        for scene in scenes:
            scene.close()
        authority_scene.close()


def test_native_server_keeps_other_client_after_peer_disconnect() -> None:
    server = net.Server(
        port=_unused_udp_port(),
        bind_address="127.0.0.1",
        peer_timeout=2,
    )
    clients = (net.Client(timeout=1, peer_timeout=2), net.Client(timeout=1, peer_timeout=2))
    server.start()
    try:
        for client in clients:
            client.connect("127.0.0.1", server.port)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and len(server.connections) != 2:
            server.poll()
            for client in clients:
                client.poll()
            time.sleep(0.001)
        assert len(server.connections) == 2
        clients[0].disconnect("peer left")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and len(server.connections) != 1:
            server.poll()
            for client in clients:
                client.poll()
            time.sleep(0.001)
        assert len(server.connections) == 1
        assert clients[1].state is net.ClientState.CONNECTED
    finally:
        for client in clients:
            if client.connection is not None:
                client.disconnect("test cleanup")
                client.poll()
        server.stop("test cleanup")
