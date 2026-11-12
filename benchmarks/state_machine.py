"""Finite StateMachine update/transition microbenchmark with no pass threshold."""

# Usage: from the repository root, run:
#   python benchmarks/state_machine.py
# This prints benchmark measurements.

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import time
import tracemalloc

from rix import StateMachine


@dataclass(frozen=True, slots=True)
class StateMachineReport:
    updates: int
    transitions: int
    update_nanoseconds: float
    transition_nanoseconds: float
    peak_bytes: int
    correct: bool


def run_benchmark(updates: int = 250_000, transitions: int = 50_000) -> StateMachineReport:
    for name, value in (("updates", updates), ("transitions", transitions)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    calls = 0
    machine = StateMachine("left")

    @machine.state("left")
    def left(_dt: float) -> None:
        nonlocal calls
        calls += 1

    @machine.state("right")
    def right(_dt: float) -> None:
        nonlocal calls
        calls += 1

    machine.update(0.0)
    calls = 0
    tracemalloc.start()
    update_start = time.perf_counter_ns()
    for _ in range(updates):
        machine.update(1.0 / 60.0)
    update_elapsed = time.perf_counter_ns() - update_start

    transition_start = time.perf_counter_ns()
    for index in range(transitions):
        machine.change("right" if index % 2 == 0 else "left")
    transition_elapsed = time.perf_counter_ns() - transition_start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return StateMachineReport(
        updates,
        transitions,
        update_elapsed / updates,
        transition_elapsed / transitions,
        peak,
        calls == updates and machine.current == ("left" if transitions % 2 == 0 else "right"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--updates", type=int, default=250_000)
    parser.add_argument("--transitions", type=int, default=50_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.updates, args.transitions)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(
            f"updates={report.updates} transitions={report.transitions} "
            f"update={report.update_nanoseconds:.1f}ns "
            f"transition={report.transition_nanoseconds:.1f}ns "
            f"peak={report.peak_bytes}B correct={report.correct}"
        )


if __name__ == "__main__":
    main()
