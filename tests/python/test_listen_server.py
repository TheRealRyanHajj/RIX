from __future__ import annotations

import time

import pytest

from easy3d import Entity, ListenServer, NetworkError, Scene, network


def _started_listen_server(
    **arguments: object,
) -> tuple[ListenServer, tuple[network.ListenEvent, ...]]:
    for port in range(32400, 32500):
        host = ListenServer(
            port=port,
            bind_address="127.0.0.1",
            **arguments,  # type: ignore[arg-type]
        )
        try:
            return host, host.start()
        except NetworkError:
            continue
    raise AssertionError("could not bind a localhost listen-server test port")


def _wait_for_role_event(
    host: ListenServer,
    *,
    role: network.ListenRole,
    event_type: network.EventType,
    local_host: bool,
) -> network.ListenEvent:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        for event in host.poll():
            if (
                event.role is role
                and event.event.type is event_type
                and event.local_host is local_host
            ):
                return event
        time.sleep(0.001)
    raise AssertionError("timed out waiting for a listen-server role event")


def test_listen_server_tags_isolated_roles_and_runs_authority_once() -> None:
    observed: list[network.ListenEvent] = []
    host, startup = _started_listen_server(
        tick_rate=120,
        on_event=lambda _host, event: observed.append(event),
    )
    scene = Scene("listen authority")

    class AuthorityLogic(Entity):
        def __init__(self) -> None:
            self.fixed_ticks = 0
            super().__init__("authority logic", scene=scene)

        def fixed_update(self, dt: float) -> None:
            assert dt == pytest.approx(1 / 120)
            self.fixed_ticks += 1

    logic = AuthorityLogic()
    host.load_scene(scene)
    try:
        assert {event.role for event in startup} == {
            network.ListenRole.AUTHORITY,
            network.ListenRole.CLIENT,
        }
        assert all(event.local_host for event in startup)
        assert len(observed) == 2
        assert host.authority_connection is not None
        assert host.client.connection is not None
        # Each transport owns its own opaque ID space. Equal numeric values are
        # deliberately disambiguated by ListenRole, never treated as identity.
        assert host.authority_connection.value == host.client.connection.value
        assert host.authority.scene is scene
        assert not hasattr(host.client, "scene")

        assert host.step() == ()
        assert host.step() == ()
        assert host.step() == ()
        assert logic.fixed_ticks == 3
        assert host.tick_count == 3
        assert host.authority.scheduler_stats.fixed_ticks == 3

        assert host.client.send(b"host input") is network.SendStatus.QUEUED
        authority_message = _wait_for_role_event(
            host,
            role=network.ListenRole.AUTHORITY,
            event_type=network.EventType.MESSAGE,
            local_host=True,
        )
        assert authority_message.event.payload == b"host input"
        assert host.authority.send(
            authority_message.event.connection, b"host snapshot"
        ) is network.SendStatus.QUEUED
        client_message = _wait_for_role_event(
            host,
            role=network.ListenRole.CLIENT,
            event_type=network.EventType.MESSAGE,
            local_host=True,
        )
        assert client_message.event.payload == b"host snapshot"

        shutdown = host.stop("listen test complete")
        assert [event.role for event in shutdown] == [
            network.ListenRole.CLIENT,
            network.ListenRole.AUTHORITY,
        ]
        assert all(
            event.event.disconnect_code is network.DisconnectCode.NORMAL
            for event in shutdown
        )
        previous_authority = authority_message.event.connection
        previous_client = client_message.event.connection
        restart = host.start()
        assert len(restart) == 2
        assert host.authority_connection is not None
        assert host.client.connection is not None
        assert host.authority_connection.value > previous_authority.value
        assert host.client.connection.value > previous_client.value
        host.stop("restart complete")
    finally:
        if host.authority.state is network.ServerState.LISTENING:
            host.stop()
        assert host.unload_scene(clear=True) is scene


def test_listen_server_distinguishes_remote_client_from_local_host() -> None:
    host, _ = _started_listen_server()
    remote = network.Client(timeout=1.0)
    try:
        remote.connect("127.0.0.1", host.port)
        remote_connected = False
        authority_connect: network.ListenEvent | None = None
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and (
            not remote_connected or authority_connect is None
        ):
            for event in host.poll():
                if (
                    event.role is network.ListenRole.AUTHORITY
                    and event.event.type is network.EventType.CONNECTED
                    and not event.local_host
                ):
                    authority_connect = event
            remote_connected = remote_connected or any(
                event.type is network.EventType.CONNECTED
                for event in remote.poll()
            )
            time.sleep(0.001)
        assert remote_connected
        assert authority_connect is not None
        assert authority_connect.event.connection != host.authority_connection
        assert len(host.authority.connections) == 2

        assert remote.send(b"remote input") is network.SendStatus.QUEUED
        remote_message = _wait_for_role_event(
            host,
            role=network.ListenRole.AUTHORITY,
            event_type=network.EventType.MESSAGE,
            local_host=False,
        )
        assert remote_message.event.connection == authority_connect.event.connection
        assert remote_message.event.payload == b"remote input"

        remote.disconnect("remote complete")
        remote.poll()
        remote_disconnect = _wait_for_role_event(
            host,
            role=network.ListenRole.AUTHORITY,
            event_type=network.EventType.DISCONNECTED,
            local_host=False,
        )
        assert remote_disconnect.event.disconnect_code is network.DisconnectCode.NORMAL
        assert host.authority.connections == (host.authority_connection,)
    finally:
        host.stop()


def test_listen_server_paced_run_does_not_duplicate_authority_callbacks() -> None:
    events: list[network.ListenEvent] = []
    host, _ = _started_listen_server(
        tick_rate=200,
        on_event=lambda _host, event: events.append(event),
    )
    scene = Scene("listen paced")

    class StopAuthority(Entity):
        def __init__(self) -> None:
            self.fixed_ticks = 0
            super().__init__("stop authority", scene=scene)

        def fixed_update(self, _dt: float) -> None:
            self.fixed_ticks += 1
            if self.fixed_ticks == 4:
                host.stop("paced listen complete")

    logic = StopAuthority()
    host.load_scene(scene)
    started = time.perf_counter()
    host.run()
    elapsed = time.perf_counter() - started
    assert logic.fixed_ticks == 4
    assert host.tick_count == 4
    assert elapsed >= 0.010
    assert elapsed < 1.0
    assert not host.is_running
    assert not host.is_started
    assert [event.role for event in events].count(network.ListenRole.AUTHORITY) == 2
    assert [event.role for event in events].count(network.ListenRole.CLIENT) == 2
    assert host.unload_scene(clear=True) is scene


def test_listen_server_start_failure_cleans_both_roles() -> None:
    for port in range(32400, 32500):
        host = ListenServer(
            port=port,
            bind_address="127.0.0.1",
            local_address="localhost",
            handshake_timeout=0.05,
        )
        try:
            with pytest.raises(ValueError, match="numeric"):
                host.start()
        except NetworkError:
            continue
        assert host.authority.state is network.ServerState.STOPPED
        assert host.client.state is network.ClientState.DISCONNECTED
        assert host.authority_connection is None
        assert not host.is_started
        break
    else:
        raise AssertionError("could not bind a listen-server failure-test port")

    def fail_callback(_host: ListenServer, _event: network.ListenEvent) -> None:
        raise RuntimeError("listen callback failed")

    for port in range(32400, 32500):
        callback_host = ListenServer(
            port=port,
            bind_address="127.0.0.1",
            handshake_timeout=0.1,
            on_event=fail_callback,
        )
        try:
            callback_host.start()
        except NetworkError:
            continue
        except RuntimeError as error:
            assert str(error) == "listen callback failed"
        else:
            raise AssertionError("failing listen callback did not propagate")
        assert callback_host.authority.state is network.ServerState.STOPPED
        assert callback_host.client.state is network.ClientState.DISCONNECTED
        assert callback_host.authority_connection is None
        break
    else:
        raise AssertionError("could not bind a callback-failure test port")
