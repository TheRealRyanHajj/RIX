"""Minimal repeatable Python-to-native call benchmark (not a performance claim)."""

# Usage: from the repository root, run:
#   python benchmarks/native_add.py
# This prints benchmark measurements.

from __future__ import annotations

import argparse
import time

from rix import native_add


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")

    value = 0
    started = time.perf_counter()
    for index in range(args.iterations):
        value = native_add(value, index & 1)
    elapsed = time.perf_counter() - started
    print(
        f"iterations={args.iterations} elapsed_seconds={elapsed:.6f} "
        f"ns_per_call={elapsed * 1e9 / args.iterations:.1f} final_value={value}"
    )


if __name__ == "__main__":
    main()

