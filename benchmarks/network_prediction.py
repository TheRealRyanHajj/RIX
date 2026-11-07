"""Finite headless native character-prediction correction benchmark."""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

from rix import Cube, Player, Scene
from rix import net


@dataclass(frozen=True, slots=True)
class PredictionCapacityReport:
    clients: int
    ticks: int
    correction_interval_ticks: int
    simulated_correction_delay_ticks: int
    inputs_submitted: int
    corrections_applied: int
    corrections_per_client_per_second: float
    replayed_inputs: int
    mean_replays_per_correction: float
    mean_position_error: float
    maximum_position_error: float
    tick_median_ms: float
    tick_p95_ms: float
    tick_p99_ms: float
    process_cpu_seconds: float
    wall_seconds: float
    process_cpu_percent: float
    rss_start_bytes: int
    rss_peak_bytes: int
    rss_end_bytes: int
    correct: bool


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999) - 1))
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
    if not get_process_memory_info(
        get_current_process(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize)


def run_prediction_capacity(
    client_count: int,
    *,
    ticks: int = 120,
    correction_interval_ticks: int = 3,
    correction_delay_ticks: int = 6,
    warmup_ticks: int = 20,
) -> PredictionCapacityReport:
    if client_count not in (2, 8, 16, 32):
        raise ValueError("client_count must be 2, 8, 16, or 32")
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 10:
        raise ValueError("ticks must be an integer of at least 10")
    for name, value in (
        ("correction_interval_ticks", correction_interval_ticks),
        ("correction_delay_ticks", correction_delay_ticks),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if (
        isinstance(warmup_ticks, bool)
        or not isinstance(warmup_ticks, int)
        or not 0 <= warmup_ticks < ticks
    ):
        raise ValueError("warmup_ticks must be an integer in [0, ticks)")

    client_scene = Scene("prediction capacity clients")
    server_scene = Scene("prediction capacity authority")
    Cube(
        scene=client_scene,
        position=(0, -0.5, 0),
        size=(max(40, client_count * 3), 1, 40),
        collider=True,
    )
    Cube(
        scene=server_scene,
        position=(0, -0.5, 0),
        size=(max(40, client_count * 3), 1, 40),
        collider=True,
    )
    client_players: list[Player] = []
    server_players: list[Player] = []
    clients: list[net.PredictedCharacterController] = []
    servers: list[net.PredictedCharacterController] = []
    for index in range(client_count):
        position = (index * 2.0 - client_count, 0.0, 0.0)
        client_player = Player(
            position=position,
            controls=False,
            scene=client_scene,
        )
        server_player = Player(
            position=position,
            controls=False,
            scene=server_scene,
        )
        client_players.append(client_player)
        server_players.append(server_player)
        clients.append(
            net.PredictedCharacterController(client_player.controller, role="client")
        )
        servers.append(
            net.PredictedCharacterController(server_player.controller, role="server")
        )

    fixed_dt = 1.0 / 60.0
    for _ in range(5):
        client_scene._native.step_physics(fixed_dt)
        server_scene._native.step_physics(fixed_dt)
    pending: list[tuple[int, int, net.CharacterCorrection]] = []
    durations: list[float] = []
    rss_start = _rss_bytes()
    rss_peak = rss_start
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    try:
        for tick in range(1, ticks + 1):
            started = time.perf_counter()
            phase = (tick // 30) % 4
            movement = (
                (0.0, 0.0, 1.0),
                (1.0, 0.0, 0.0),
                (0.0, 0.0, -1.0),
                (-1.0, 0.0, 0.0),
            )[phase]
            for index, (client, server) in enumerate(zip(clients, servers, strict=True)):
                command = client.submit(
                    movement,
                    heading_degrees=float(phase * 90),
                    sprint=(index + tick) % 2 == 0,
                )
                server.accept(command)
            client_scene._native.step_physics(fixed_dt)
            server_scene._native.step_physics(fixed_dt)
            if tick % correction_interval_ticks == 0:
                for index, server in enumerate(servers):
                    pending.append(
                        (
                            tick + correction_delay_ticks,
                            index,
                            server.make_correction(tick),
                        )
                    )
            ready = tuple(item for item in pending if item[0] <= tick)
            if ready:
                pending = [item for item in pending if item[0] > tick]
                for _delivery_tick, index, correction in ready:
                    clients[index].reconcile(
                        correction,
                        fixed_delta_seconds=fixed_dt,
                    )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if tick > warmup_ticks:
                durations.append(elapsed_ms)
            rss_peak = max(rss_peak, _rss_bytes())

        # Deliver the ordered delayed tail, including the final authoritative
        # correction. No new inputs are submitted, so the last correction
        # leaves every client at the exact server state.
        for _delivery_tick, index, correction in pending:
            clients[index].reconcile(correction, fixed_delta_seconds=fixed_dt)

        wall_seconds = time.perf_counter() - wall_start
        cpu_seconds = time.process_time() - cpu_start
        stats = tuple(client.correction_stats for client in clients)
        corrections = sum(item.corrections for item in stats)
        replayed = sum(item.replayed_inputs for item in stats)
        total_error = sum(item.total_position_error for item in stats)
        maximum_error = max((item.maximum_position_error for item in stats), default=0.0)
        correct = all(
            client_player.position.almost_equal(server_player.position, 1.0e-4)
            and client_player.controller.linear_velocity.almost_equal(
                server_player.controller.linear_velocity, 1.0e-4
            )
            and client.pending_inputs == ()
            for client_player, server_player, client in zip(
                client_players, server_players, clients, strict=True
            )
        )
        return PredictionCapacityReport(
            client_count,
            ticks,
            correction_interval_ticks,
            correction_delay_ticks,
            client_count * ticks,
            corrections,
            corrections / client_count / (ticks * fixed_dt),
            replayed,
            replayed / corrections if corrections else 0.0,
            total_error / corrections if corrections else 0.0,
            maximum_error,
            statistics.median(durations),
            _percentile(durations, 0.95),
            _percentile(durations, 0.99),
            cpu_seconds,
            wall_seconds,
            cpu_seconds / wall_seconds * 100.0 if wall_seconds else 0.0,
            rss_start,
            rss_peak,
            _rss_bytes(),
            correct,
        )
    finally:
        client_scene.close()
        server_scene.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, choices=(2, 8, 16, 32))
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--correction-interval", type=int, default=3)
    parser.add_argument("--correction-delay", type=int, default=6)
    parser.add_argument("--warmup-ticks", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.clients is not None:
        reports = [
            run_prediction_capacity(
                args.clients,
                ticks=args.ticks,
                correction_interval_ticks=args.correction_interval,
                correction_delay_ticks=args.correction_delay,
                warmup_ticks=args.warmup_ticks,
            )
        ]
    else:
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
                    "--correction-interval",
                    str(args.correction_interval),
                    "--correction-delay",
                    str(args.correction_delay),
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
                    f"{count}-client prediction process failed:\n"
                    f"stdout:\n{child.stdout}\nstderr:\n{child.stderr}"
                )
            payload = json.loads(child.stdout)
            reports.append(PredictionCapacityReport(**payload[0]))
    if args.json:
        print(json.dumps([asdict(report) for report in reports], indent=2))
    else:
        for report in reports:
            print(
                f"clients={report.clients} correct={report.correct} "
                f"tick_ms median/p95/p99={report.tick_median_ms:.3f}/"
                f"{report.tick_p95_ms:.3f}/{report.tick_p99_ms:.3f} "
                f"corrections={report.corrections_applied} "
                f"rate={report.corrections_per_client_per_second:.1f}/client/s "
                f"replays/correction={report.mean_replays_per_correction:.2f} "
                f"error mean/max={report.mean_position_error:.4f}/"
                f"{report.maximum_position_error:.4f}"
            )
    if not all(report.correct for report in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
