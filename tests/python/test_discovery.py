from __future__ import annotations

import socket
import struct
import time

import pytest

import easy3d
from easy3d import discovery


def _unused_udp_port() -> int:
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udp.bind(("127.0.0.1", 0))
        return int(udp.getsockname()[1])
    finally:
        udp.close()


def _exchange(
    announcer: discovery.LanDiscoveryAnnouncer,
    browser: discovery.LanDiscoveryBrowser,
    *,
    timeout: float = 1.0,
) -> tuple[discovery.DiscoveredServer, ...]:
    browser.refresh()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        announcer.poll()
        found = browser.poll()
        if found:
            return found
        time.sleep(0.001)
    return ()


def test_codec_rejects_malformed_and_unbounded_fields() -> None:
    query = discovery._encode_query(42)
    assert discovery._decode_query(query) == 42
    with pytest.raises(ValueError):
        discovery._encode_query(0)
    with pytest.raises(ValueError):
        discovery._decode_query(query[:-1])

    response = discovery._encode_response(42, 7, 7777, 1, 3, b"Local game")
    assert discovery._decode_response(response) == (
        42,
        7,
        7777,
        1,
        3,
        "Local game",
    )

    malformed = bytearray(response)
    malformed[7] = 1  # reserved flags
    with pytest.raises(ValueError):
        discovery._decode_response(bytes(malformed))
    malformed = bytearray(response)
    malformed[-1] = 0xFF
    with pytest.raises(ValueError):
        discovery._decode_response(bytes(malformed))
    with pytest.raises(ValueError):
        discovery._decode_response(response + b"trailing")
    with pytest.raises(ValueError):
        discovery._decode_response(b"x" * (discovery.MAX_DATAGRAM_SIZE + 1))
    with pytest.raises(ValueError):
        discovery.LanDiscoveryAnnouncer("bad\nname", 7777)
    with pytest.raises(ValueError):
        discovery.LanDiscoveryAnnouncer("x" * 129, 7777)


def test_real_loopback_query_response_is_explicit_and_compatible() -> None:
    port = _unused_udp_port()
    announcer = discovery.LanDiscoveryAnnouncer(
        "Test server",
        32123,
        discovery_port=port,
        bind_address="127.0.0.1",
        instance_id=99,
    )
    browser = discovery.LanDiscoveryBrowser(
        discovery_port=port,
        bind_address="127.0.0.1",
        target_address="127.0.0.1",
    )
    with announcer, browser:
        assert browser.poll() == ()
        found = _exchange(announcer, browser)
        assert len(found) == 1
        assert found[0].instance_id == 99
        assert found[0].name == "Test server"
        assert found[0].address == "127.0.0.1"
        assert found[0].port == 32123
        assert found[0].compatible
        assert browser.servers == found
        assert announcer.stats.queries_received == 1
        assert announcer.stats.responses_sent == 1
        assert browser.stats.queries_sent == 1
        assert browser.stats.responses_received == 1
    assert not announcer.is_running
    assert not browser.is_running


def test_nonce_filter_rate_limit_expiry_and_restart() -> None:
    port = _unused_udp_port()
    announcer = discovery.LanDiscoveryAnnouncer(
        "Bounded",
        7777,
        discovery_port=port,
        bind_address="127.0.0.1",
        minimum_response_interval=0.05,
    )
    browser = discovery.LanDiscoveryBrowser(
        discovery_port=port,
        bind_address="127.0.0.1",
        target_address="127.0.0.1",
        result_ttl=0.02,
    )
    announcer.start()
    browser.start()
    try:
        assert _exchange(announcer, browser)
        active_nonce = browser.refresh()
        deadline = time.monotonic() + 0.2
        while announcer.stats.rate_limited == 0 and time.monotonic() < deadline:
            announcer.poll()
            time.sleep(0.001)
        assert announcer.stats.rate_limited == 1
        assert browser.poll() == ()

        raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            wrong = discovery._encode_response(
                1, 123, 7777, 1, 1, b"forged nonce"
            )
            raw.sendto(wrong, ("127.0.0.1", browser.local_port))
            wrong_port = discovery._encode_response(
                active_nonce, 124, 7777, 1, 1, b"wrong source port"
            )
            raw.sendto(wrong_port, ("127.0.0.1", browser.local_port))
        finally:
            raw.close()
        deadline = time.monotonic() + 0.2
        while (
            (
                browser.stats.unmatched_responses == 0
                or browser.stats.malformed_packets == 0
            )
            and time.monotonic() < deadline
        ):
            browser.poll()
            time.sleep(0.001)
        assert browser.stats.unmatched_responses == 1
        assert browser.stats.malformed_packets == 1

        deadline = time.monotonic() + 0.2
        while browser.servers and time.monotonic() < deadline:
            time.sleep(0.005)
        assert browser.servers == ()
    finally:
        browser.close()
        announcer.close()

    announcer.start()
    browser.start()
    try:
        time.sleep(0.055)
        assert _exchange(announcer, browser)
    finally:
        browser.close()
        announcer.close()


def test_cache_capacity_incompatibility_malformed_input_and_port_collision() -> None:
    port = _unused_udp_port()
    announcer = discovery.LanDiscoveryAnnouncer(
        "First",
        7001,
        discovery_port=port,
        bind_address="127.0.0.1",
        protocol_version=2,
        schema_version=9,
    )
    collision = discovery.LanDiscoveryAnnouncer(
        "Second",
        7002,
        discovery_port=port,
        bind_address="127.0.0.1",
    )
    browser = discovery.LanDiscoveryBrowser(
        discovery_port=port,
        bind_address="127.0.0.1",
        target_address="127.0.0.1",
        cache_capacity=1,
    )
    announcer.start()
    browser.start()
    try:
        with pytest.raises(easy3d.NetworkError):
            collision.start()
        found = _exchange(announcer, browser)
        assert len(found) == 1
        assert not found[0].compatible

        announcer.close()
        raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            raw.bind(("127.0.0.1", port))
            query_nonce = browser.refresh()
            forged = discovery._encode_response(
                query_nonce, 555, 7003, 1, 1, b"Replacement"
            )
            raw.sendto(b"not discovery", ("127.0.0.1", browser.local_port))
            raw.sendto(forged, ("127.0.0.1", browser.local_port))
        finally:
            raw.close()
        deadline = time.monotonic() + 0.2
        while browser.stats.responses_received < 2 and time.monotonic() < deadline:
            browser.poll()
            time.sleep(0.001)
        assert browser.stats.malformed_packets == 1
        assert browser.stats.cache_evictions == 1
        assert len(browser.servers) == 1
        assert browser.servers[0].name == "Replacement"
    finally:
        browser.close()
        announcer.close()
        collision.close()


@pytest.mark.parametrize(
    ("constructor", "arguments"),
    [
        (discovery.LanDiscoveryAnnouncer, ("name", 0)),
        (discovery.LanDiscoveryAnnouncer, ("name", 65536)),
        (discovery.LanDiscoveryBrowser, ()),
    ],
)
def test_lifecycle_requires_explicit_start(constructor: object, arguments: tuple[object, ...]) -> None:
    if constructor is discovery.LanDiscoveryBrowser:
        owner = discovery.LanDiscoveryBrowser(target_address="127.0.0.1")
        with pytest.raises(easy3d.NetworkError):
            owner.refresh()
        with pytest.raises(easy3d.NetworkError):
            owner.poll()
    else:
        with pytest.raises(ValueError):
            discovery.LanDiscoveryAnnouncer(*arguments)


def test_response_prefix_stays_fixed_and_bounded() -> None:
    response = discovery._encode_response(
        1, 2, 3, 4, 5, "é".encode("utf-8") * 64
    )
    assert len(response) <= discovery.MAX_DATAGRAM_SIZE
    magic, version, message_type, flags, size = struct.unpack_from("<4sHBBI", response)
    assert (magic, version, message_type, flags) == (b"E3DD", 1, 2, 0)
    assert size == len(response) - 12


def test_announcer_caps_work_per_poll() -> None:
    port = _unused_udp_port()
    announcer = discovery.LanDiscoveryAnnouncer(
        "Capped",
        7777,
        discovery_port=port,
        bind_address="127.0.0.1",
        max_packets_per_poll=2,
    )
    raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    announcer.start()
    try:
        for _ in range(3):
            raw.sendto(b"malformed", ("127.0.0.1", port))
        time.sleep(0.02)
        assert announcer.poll(999) == 0
        assert announcer.stats.malformed_packets == 2
        assert announcer.poll(999) == 0
        assert announcer.stats.malformed_packets == 3
    finally:
        raw.close()
        announcer.close()


def test_root_exports_are_typed_public_classes() -> None:
    assert easy3d.LanDiscoveryAnnouncer is discovery.LanDiscoveryAnnouncer
    assert easy3d.LanDiscoveryBrowser is discovery.LanDiscoveryBrowser
