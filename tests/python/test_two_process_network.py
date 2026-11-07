from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "06_two_process" / "main.py"


def _unused_udp_port() -> int:
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp.bind(("127.0.0.1", 0))
        return int(udp.getsockname()[1])
    finally:
        udp.close()


def _launch(*arguments: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-u", str(SAMPLE), *arguments],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _wait_ready(process: subprocess.Popen[str], marker: Path) -> None:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if marker.is_file():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"child exited before ready: code={process.returncode}\n"
                f"stdout={stdout}\nstderr={stderr}"
            )
        time.sleep(0.005)
    pytest.fail("child did not publish readiness before its deadline")


def _reap(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        process.kill()
    return process.communicate(timeout=5.0)


def _server_arguments(port: int, marker: Path, *, one_shot: bool) -> list[str]:
    arguments = [
        "server",
        "--bind",
        "127.0.0.1",
        "--port",
        str(port),
        "--timeout",
        "20",
        "--peer-timeout",
        "2",
        "--ready-file",
        str(marker),
    ]
    if one_shot:
        arguments.append("--one-shot")
    return arguments


def test_sample_exchanges_bytes_across_two_processes(tmp_path: Path) -> None:
    port = _unused_udp_port()
    marker = tmp_path / "server.ready"
    server = _launch(*_server_arguments(port, marker, one_shot=True))
    try:
        _wait_ready(server, marker)
        client = subprocess.run(
            [
                sys.executable,
                "-u",
                str(SAMPLE),
                "client",
                "--address",
                "127.0.0.1",
                "--port",
                str(port),
                "--timeout",
                "8",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=12.0,
            check=False,
        )
        server_stdout, server_stderr = server.communicate(timeout=12.0)
        assert client.returncode == 0, client.stdout + client.stderr
        assert server.returncode == 0, server_stdout + server_stderr
        assert "CLIENT_CONNECTED" in client.stdout
        assert "CLIENT_SENT request=ping" in client.stdout
        assert "CLIENT_RECEIVED response=pong" in client.stdout
        assert "CLIENT_DONE exchange=complete" in client.stdout
        assert "SERVER_RECEIVED request=ping" in server_stdout
        assert "SERVER_DONE exchange=complete" in server_stdout
        assert client.stderr == ""
        assert server_stderr == ""
    finally:
        _reap(server)


def test_sample_recovers_reliably_under_adverse_two_process_impairment(
    tmp_path: Path,
) -> None:
    port = _unused_udp_port()
    marker = tmp_path / "impaired-server.ready"
    server = _launch(
        *_server_arguments(port, marker, one_shot=True),
        "--profile",
        "adverse",
    )
    try:
        _wait_ready(server, marker)
        client = subprocess.run(
            [
                sys.executable,
                "-u",
                str(SAMPLE),
                "client",
                "--address",
                "127.0.0.1",
                "--port",
                str(port),
                "--timeout",
                "15",
                "--profile",
                "adverse",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20.0,
            check=False,
        )
        server_stdout, server_stderr = server.communicate(timeout=20.0)
        assert client.returncode == 0, client.stdout + client.stderr
        assert server.returncode == 0, server_stdout + server_stderr
        assert "CLIENT_RECEIVED response=pong" in client.stdout
        assert "CLIENT_DONE exchange=complete" in client.stdout
        assert "SERVER_RECEIVED request=ping" in server_stdout
        assert "SERVER_DONE exchange=complete" in server_stdout
        assert client.stderr == ""
        assert server_stderr == ""
    finally:
        _reap(server)


def test_gameplay_port_collision_leaves_first_process_usable(
    tmp_path: Path,
) -> None:
    port = _unused_udp_port()
    first_marker = tmp_path / "first.ready"
    first = _launch(*_server_arguments(port, first_marker, one_shot=True))
    try:
        _wait_ready(first, first_marker)
        collision = subprocess.run(
            [
                sys.executable,
                "-u",
                str(SAMPLE),
                "server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--timeout",
                "1",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=8.0,
            check=False,
        )
        assert collision.returncode == 2
        assert "SERVER_START_FAILED" in collision.stderr

        client = subprocess.run(
            [
                sys.executable,
                "-u",
                str(SAMPLE),
                "client",
                "--address",
                "127.0.0.1",
                "--port",
                str(port),
                "--timeout",
                "8",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=12.0,
            check=False,
        )
        stdout, stderr = first.communicate(timeout=12.0)
        assert client.returncode == 0, client.stdout + client.stderr
        assert first.returncode == 0, stdout + stderr
        assert "SERVER_DONE exchange=complete" in stdout
    finally:
        _reap(first)


def test_client_observes_abrupt_server_process_loss(tmp_path: Path) -> None:
    port = _unused_udp_port()
    server_marker = tmp_path / "abrupt-server.ready"
    client_marker = tmp_path / "abrupt-client.ready"
    server = _launch(*_server_arguments(port, server_marker, one_shot=False))
    client: subprocess.Popen[str] | None = None
    try:
        _wait_ready(server, server_marker)
        client = _launch(
            "client",
            "--address",
            "127.0.0.1",
            "--port",
            str(port),
            "--timeout",
            "20",
            "--peer-timeout",
            "2",
            "--expect-disconnect",
            "--ready-file",
            str(client_marker),
        )
        _wait_ready(client, client_marker)
        server.kill()  # Deliberately bypasses RIX's graceful stop path.
        server.communicate(timeout=5.0)
        client_stdout, client_stderr = client.communicate(timeout=22.0)
        assert client.returncode == 0, client_stdout + client_stderr
        assert "CLIENT_CONNECTED" in client_stdout
        assert "CLIENT_DISCONNECTED" in client_stdout
        assert "CLIENT_DONE abrupt_disconnect=observed" in client_stdout
        assert client_stderr == ""
    finally:
        _reap(server)
        if client is not None:
            _reap(client)
def test_server_observes_abrupt_client_process_loss(tmp_path: Path) -> None:
    port = _unused_udp_port()
    server_marker = tmp_path / "client-loss-server.ready"
    server_connection = tmp_path / "client-loss-server.connected"
    client_marker = tmp_path / "client-loss-client.ready"
    server = _launch(
        *_server_arguments(port, server_marker, one_shot=True),
        "--connection-file",
        str(server_connection),
    )
    client: subprocess.Popen[str] | None = None
    try:
        _wait_ready(server, server_marker)
        client = _launch(
            "client",
            "--address",
            "127.0.0.1",
            "--port",
            str(port),
            "--timeout",
            "20",
            "--peer-timeout",
            "2",
            "--expect-disconnect",
            "--ready-file",
            str(client_marker),
        )
        _wait_ready(client, client_marker)
        _wait_ready(server, server_connection)
        client.kill()  # Leaves the server to detect transport liveness loss.
        client.communicate(timeout=5.0)
        server_stdout, server_stderr = server.communicate(timeout=22.0)
        assert server.returncode == 4, server_stdout + server_stderr
        assert "SERVER_CONNECTED" in server_stdout
        assert "SERVER_DISCONNECTED" in server_stdout
        assert "SERVER_PEER_LOST exchange=incomplete" in server_stdout
        assert server_stderr == ""
    finally:
        _reap(server)
        if client is not None:
            _reap(client)
