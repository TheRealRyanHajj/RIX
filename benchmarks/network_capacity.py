"""Finite real-loopback RIX multiplayer capacity benchmark."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

from rix import Entity, Scene
from rix import net as network
from rix.net import NetworkError, Server
from rix.net import replication


PLAYER = 1
LOAD = 1


@dataclass(frozen=True, slots=True)
class CapacityReport:
    clients: int
    ticks: int
    correct: bool
    tick_median_ms: float
    tick_p95_ms: float
    tick_p99_ms: float
    tick_max_ms: float
    observation_latency_median_ms: float
    observation_latency_p95_ms: float
    process_cpu_seconds: float
    wall_seconds: float
    process_cpu_percent: float
    rss_start_bytes: int
    rss_peak_bytes: int
    rss_end_bytes: int
    server_bytes_sent: int
    client_bytes_received: int
    server_bytes_per_second: float
    bytes_per_second_per_client: float
    transform_frames_queued: int
    transform_frames_budget_deferred: int
    transport_messages_lost: int = 0
    transport_queue_rejections: int = 0
    transport_event_overflows: int = 0
    client_pending_bytes_peak: int = 0
    transform_frames_backpressured: int = 0
    transform_full_snapshots: int = 0
    transform_delta_snapshots: int = 0
    transform_snapshot_bytes: int = 0
    transform_snapshot_mean_bytes: float = 0.0


@dataclass(frozen=True, slots=True)
class CapacityBudget:
    """Post-baseline limits for the documented single-process workload."""

    tick_p99_ms: float = 100.0
    observation_latency_p95_ms: float = 50.0
    process_cpu_percent: float = 200.0
    rss_peak_bytes: int = 128 * 1024 * 1024
    server_bytes_per_tick: float = 80 * 1024


DEFAULT_BUDGET = CapacityBudget()


def budget_failures(
    report: CapacityReport, budget: CapacityBudget = DEFAULT_BUDGET
) -> tuple[str, ...]:
    failures: list[str] = []
    if not report.correct:
        failures.append("replicated final state is incorrect")
    if report.transform_frames_budget_deferred:
        failures.append("transform frames were budget-deferred")
    for label, measured, limit in (
        ("tick p99 ms", report.tick_p99_ms, budget.tick_p99_ms),
        (
            "observation latency p95 ms",
            report.observation_latency_p95_ms,
            budget.observation_latency_p95_ms,
        ),
        ("process CPU percent", report.process_cpu_percent, budget.process_cpu_percent),
        ("RSS peak bytes", float(report.rss_peak_bytes), float(budget.rss_peak_bytes)),
        (
            "server bytes per tick",
            report.server_bytes_sent / report.ticks,
            budget.server_bytes_per_tick,
        ),
    ):
        if measured > limit:
            failures.append(f"{label} {measured:.3f} exceeds {limit:.3f}")
    return tuple(failures)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        return 0

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.argtypes = []
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    get_process_memory_info.restype = ctypes.c_int
    process = get_current_process()
    ok = get_process_memory_info(process, ctypes.byref(counters), counters.cb)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize)


def _server(on_connect, on_disconnect, clients: int) -> Server:  # type: ignore[no-untyped-def]
    for port in range(33100, 33200):
        server = Server(
            port=port,
            max_players=clients,
            bind_address="127.0.0.1",
            peer_timeout=5,
            event_queue_capacity=max(4096, clients * clients * 4),
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        try:
            server.start()
            return server
        except NetworkError:
            continue
    raise RuntimeError("no loopback benchmark port is available")


def _pump(server: Server, mirrors: list[replication.ClientReplication], predicate) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not predicate():
        server.poll(maximum_events=16384)
        for mirror in mirrors:
            mirror.poll(maximum_events=4096)
        time.sleep(0.001)
    if not predicate():
        raise RuntimeError("capacity benchmark timed out")


def run_capacity(client_count: int, *, ticks: int = 120, warmup_ticks: int = 20) -> CapacityReport:
    if isinstance(client_count, bool) or not isinstance(client_count, int):
        raise TypeError("client_count must be an integer")
    if client_count not in (2, 8, 16, 32):
        raise ValueError("client_count must be 2, 8, 16, or 32")
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 10:
        raise ValueError("ticks must be an integer of at least 10")
    if (
        isinstance(warmup_ticks, bool)
        or not isinstance(warmup_ticks, int)
        or not 0 <= warmup_ticks < ticks
    ):
        raise ValueError("warmup_ticks must be an integer in [0, ticks)")

    registry = replication.PrefabRegistry(schema_version=16)
    registry.register(PLAYER, "bot", lambda scene: Entity("bot", scene=scene))
    registry.register_variable(PLAYER, LOAD, "load", "int", 0, max_bytes=8)
    registry.register_transform(PLAYER)
    owner_box: list[replication.ServerReplication] = []
    players: dict[network.ConnectionId, replication.ReplicatedObject] = {}

    def connected(_server: Server, connection: network.ConnectionId) -> None:
        owner = owner_box[0]
        bot = owner.spawn(PLAYER)
        index = len(players)
        bot.entity.position = (float(index), 0.0, 0.0)
        owner.set_owner(bot.id, connection)
        players[connection] = bot

    def disconnected(_server: Server, event: network.NetworkEvent) -> None:
        bot = players.pop(event.connection, None)
        if bot is not None and any(item.id == bot.id for item in owner_box[0].objects):
            owner_box[0].despawn(bot.id)

    server = _server(connected, disconnected, client_count)
    server.load_scene(Scene("capacity authority"))
    owner = replication.ServerReplication(
        server,
        registry,
        max_objects=client_count + 8,
        max_transform_sends=client_count * client_count * 2,
        # Capacity runs intentionally exercise the dense all-to-all case. Keep
        # the application-level shaper above its 32-client wire rate so this
        # benchmark measures the transport/replication path instead of the
        # lower default gameplay budget (covered separately by unit tests).
        transform_budget_bytes_per_second=16 * 1024 * 1024,
        transform_budget_burst_bytes=4 * 1024 * 1024,
        transform_tick_rate=60,
    )
    owner_box.append(owner)
    clients: list[network.Client] = []
    mirrors: list[replication.ClientReplication] = []
    rss_start = _rss_bytes()
    rss_peak = rss_start
    try:
        for index in range(client_count):
            client = network.Client(
                timeout=3,
                peer_timeout=5,
                event_queue_capacity=max(1024, client_count * 8),
            )
            mirror = replication.ClientReplication(
                client,
                Scene(f"capacity client {index}"),
                registry,
                max_objects=client_count + 8,
                max_transform_samples=8,
            )
            clients.append(client)
            mirrors.append(mirror)
            client.connect("127.0.0.1", server.port)
        _pump(
            server,
            mirrors,
            lambda: len(players) == client_count
            and all(mirror.is_synchronized for mirror in mirrors)
            and all(len(mirror.objects) == client_count for mirror in mirrors),
        )
        # Early clients connect before later bots exist, so send one complete
        # unmeasured transform frame to establish every connection/object
        # baseline. Drain its ACKs before measured delta traffic.
        initial_flush = owner.flush_transforms(0)
        _pump(
            server,
            mirrors,
            lambda: len(owner._transform_baselines) == client_count * client_count
            and all(
                all(
                    mirror.transform_snapshots(item.id)
                    and mirror.transform_snapshots(item.id)[-1].sequence
                    == initial_flush.sequence
                    for item in mirror.objects
                )
                for mirror in mirrors
            ),
        )

        durations: list[float] = []
        observation_latencies: list[float] = []
        send_times: dict[int, float] = {}
        last_seen: dict[int, int] = {}
        queued = 0
        deferred = 0
        backpressured = 0
        full_snapshots = 0
        delta_snapshots = 0
        snapshot_bytes = 0
        pending_bytes_peak = 0
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        ordered_players = tuple(players.values())
        sentinel_id = ordered_players[0].id
        for tick in range(1, ticks + 1):
            tick_start = time.perf_counter()
            for index, bot in enumerate(ordered_players):
                bot.entity.position = (
                    float(index),
                    0.0,
                    tick * 0.01 + (index % 4) * 0.1,
                )
                if tick % 30 == 0:
                    owner.variable(bot.id, LOAD).value = tick
            if tick % 30 == 0:
                owner.flush()
            flush = owner.flush_transforms(tick)
            queued += flush.queued
            deferred += flush.budget_deferred
            backpressured += flush.backpressured
            full_snapshots += flush.full_snapshots
            delta_snapshots += flush.delta_snapshots
            snapshot_bytes += flush.bytes_queued
            send_times[flush.sequence] = time.perf_counter()
            server.poll(maximum_events=16384)
            for mirror_index, mirror in enumerate(mirrors):
                mirror.poll(maximum_events=4096)
                # One stable sentinel per connection measures fan-out latency
                # without making O(clients²) history inspection part of every
                # timed tick. Final correctness still validates every replica.
                history = mirror.transform_snapshots(sentinel_id)
                if history:
                    sequence = history[-1].sequence
                    if (
                        sequence > last_seen.get(mirror_index, 0)
                        and sequence in send_times
                    ):
                        observation_latencies.append(
                            (time.perf_counter() - send_times[sequence]) * 1000.0
                        )
                        last_seen[mirror_index] = sequence
            pending_bytes_peak = max(
                pending_bytes_peak,
                *(
                    client.metrics.pending_reliable_bytes
                    + client.metrics.pending_unreliable_bytes
                    for client in clients
                ),
            )
            elapsed_ms = (time.perf_counter() - tick_start) * 1000.0
            if tick > warmup_ticks:
                durations.append(elapsed_ms)
            rss_peak = max(rss_peak, _rss_bytes())
            # Give the loopback socket worker a bounded scheduling opportunity.
            time.sleep(0.0005)

        final_sequence = owner.last_transform_flush.sequence
        _pump(
            server,
            mirrors,
            lambda: all(
                all(
                    mirror.transform_snapshots(item.id)
                    and mirror.transform_snapshots(item.id)[-1].sequence
                    == final_sequence
                    for item in mirror.objects
                )
                for mirror in mirrors
            ),
        )
        wall_seconds = time.perf_counter() - wall_start
        cpu_seconds = time.process_time() - cpu_start
        correct = all(len(mirror.objects) == client_count for mirror in mirrors)
        for mirror in mirrors:
            for item in mirror.objects:
                expected = ordered_players[item.id.value - 1].entity.position
                actual = mirror.transform_snapshots(item.id)[-1].position
                correct = correct and actual.almost_equal(expected, 0.011)
                correct = correct and int(mirror.variable(item.id, LOAD).value) == (
                    ticks - ticks % 30
                )
        server_stats = server.stats
        client_stats = tuple(client.stats for client in clients)
        received = sum(stats.bytes_received for stats in client_stats)
        messages_lost = server_stats.messages_lost + sum(
            stats.messages_lost for stats in client_stats
        )
        queue_rejections = server_stats.queue_rejections + sum(
            stats.queue_rejections for stats in client_stats
        )
        event_overflows = server_stats.event_overflows + sum(
            stats.event_overflows for stats in client_stats
        )
        rss_end = _rss_bytes()
        return CapacityReport(
            client_count,
            ticks,
            correct,
            statistics.median(durations),
            _percentile(durations, 0.95),
            _percentile(durations, 0.99),
            max(durations),
            statistics.median(observation_latencies) if observation_latencies else 0.0,
            _percentile(observation_latencies, 0.95),
            cpu_seconds,
            wall_seconds,
            cpu_seconds / wall_seconds * 100.0 if wall_seconds else 0.0,
            rss_start,
            rss_peak,
            rss_end,
            server_stats.bytes_sent,
            received,
            server_stats.bytes_sent / wall_seconds,
            server_stats.bytes_sent / wall_seconds / client_count,
            queued,
            deferred,
            messages_lost,
            queue_rejections,
            event_overflows,
            pending_bytes_peak,
            backpressured,
            full_snapshots,
            delta_snapshots,
            snapshot_bytes,
            snapshot_bytes / queued if queued else 0.0,
        )
    finally:
        for mirror in mirrors:
            mirror.clear()
        for client in clients:
            if client.connection is not None:
                client.disconnect("capacity benchmark complete")
                client.poll()
        owner.close(destroy=True)
        server.stop()
        server.unload_scene(clear=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, choices=(2, 8, 16, 32))
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--warmup-ticks", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--enforce-budget",
        action="store_true",
        help="exit nonzero if a post-baseline workload budget is exceeded",
    )
    args = parser.parse_args()
    if args.clients is not None:
        reports = [
            run_capacity(
                args.clients,
                ticks=args.ticks,
                warmup_ticks=args.warmup_ticks,
            )
        ]
    else:
        # A separate process gives every count a clean GNS runtime, allocator,
        # port lifecycle, and RSS baseline. Sequential in-process runs can
        # retain backend worker state long enough to make the next dense
        # all-to-all final drain time out, and the resulting memory figures are
        # not comparable baselines.
        reports = []
        sample = Path(__file__).resolve()
        for count in (2, 8, 16, 32):
            child = subprocess.run(
                [
                    sys.executable,
                    str(sample),
                    "--clients",
                    str(count),
                    "--ticks",
                    str(args.ticks),
                    "--warmup-ticks",
                    str(args.warmup_ticks),
                    "--json",
                ],
                cwd=sample.parents[1],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if child.returncode != 0:
                raise RuntimeError(
                    f"{count}-client benchmark process failed:\n"
                    f"stdout:\n{child.stdout}\nstderr:\n{child.stderr}"
                )
            payload = json.loads(child.stdout)
            if not isinstance(payload, list) or len(payload) != 1:
                raise RuntimeError(
                    f"{count}-client benchmark returned an invalid report"
                )
            reports.append(CapacityReport(**payload[0]))
    if args.json:
        print(json.dumps([asdict(report) for report in reports], indent=2))
    else:
        for report in reports:
            print(
                f"clients={report.clients} correct={report.correct} "
                f"tick_ms median/p95/p99/max={report.tick_median_ms:.3f}/"
                f"{report.tick_p95_ms:.3f}/{report.tick_p99_ms:.3f}/"
                f"{report.tick_max_ms:.3f} cpu={report.process_cpu_percent:.1f}% "
                f"rss_peak={report.rss_peak_bytes / (1024 * 1024):.1f}MiB "
                f"server={report.server_bytes_per_second / 1024:.1f}KiB/s "
                f"per_client={report.bytes_per_second_per_client / 1024:.1f}KiB/s "
                f"latency_p95={report.observation_latency_p95_ms:.3f}ms "
                f"snapshot_mean={report.transform_snapshot_mean_bytes:.1f}B "
                f"lost/rejected/overflow={report.transport_messages_lost}/"
                f"{report.transport_queue_rejections}/"
                f"{report.transport_event_overflows} "
                f"pending_peak={report.client_pending_bytes_peak}B "
                f"deferred/backpressured="
                f"{report.transform_frames_budget_deferred}/"
                f"{report.transform_frames_backpressured}"
            )
    failures = tuple(
        f"{report.clients} clients: {failure}"
        for report in reports
        for failure in budget_failures(report)
    )
    if args.enforce_budget and failures:
        for failure in failures:
            print(f"BUDGET FAILURE: {failure}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
