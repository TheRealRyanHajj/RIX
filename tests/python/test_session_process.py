from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import sys


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_session_communicates_between_independent_processes() -> None:
    helper = Path(__file__).parent / "helpers" / "session_process.py"
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-u", str(helper), "server", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert server.stdout is not None
        assert server.stdout.readline().strip() == "READY"
        client = subprocess.run(
            [sys.executable, "-u", str(helper), "client", str(port)],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        assert client.returncode == 0, client.stderr
        assert client.stdout.strip() == "PONG 42"
        server_stdout, server_stderr = server.communicate(timeout=12)
        assert server.returncode == 0, server_stderr
        assert server_stdout == ""
    finally:
        if server.poll() is None:
            server.kill()
            server.communicate()
