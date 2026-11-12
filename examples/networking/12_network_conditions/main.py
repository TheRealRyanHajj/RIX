"""Compare deterministic latency, jitter, and loss profiles without sockets."""

# Usage: from the repository root, run:
#   python examples/networking/12_network_conditions/main.py
# See the nearby README for setup and startup order.

from __future__ import annotations

import argparse
from dataclasses import dataclass

from rix import net


@dataclass(frozen=True, slots=True)
class Result:
    profile: str
    sent: int
    delivered: int
    lost: int
    first_delivery_ms: float | None
    last_delivery_ms: float | None


def simulate(
    profile: net.NetworkCondition,
    *,
    messages: int = 200,
    seed: int = 53,
) -> Result:
    """Run one repeatable packet-level simulation and return its measurements."""

    if messages < 1:
        raise ValueError("messages must be positive")
    link = profile.create_simulated_link(seed=seed)
    # Consume the two synthetic CONNECTED events before measuring messages.
    link.first.poll()
    link.second.poll()

    for sequence in range(messages):
        payload = sequence.to_bytes(4, "little")
        status = link.first.send(payload, delivery=net.Delivery.UNRELIABLE)
        if status is not net.SendStatus.QUEUED:
            raise RuntimeError(f"simulator rejected message {sequence}: {status.value}")

    delivered = 0
    first_delivery: float | None = None
    last_delivery: float | None = None
    # Advance virtual time rather than sleeping, so the result is fast and
    # exactly reproducible for a given seed.
    step = 0.001
    deadline = profile.one_way_latency_seconds + profile.jitter_seconds + 0.010
    while link.time_seconds < deadline or link.in_flight_count:
        link.advance(step)
        for event in link.second.poll(maximum_events=max(256, messages)):
            if event.type is not net.EventType.MESSAGE:
                continue
            delivered += 1
            first_delivery = (
                link.time_seconds if first_delivery is None else first_delivery
            )
            last_delivery = link.time_seconds

    lost = link.first.stats.messages_lost
    if delivered + lost != messages:
        raise RuntimeError("delivered and lost counts do not account for every message")
    return Result(
        profile.name,
        messages,
        delivered,
        lost,
        None if first_delivery is None else first_delivery * 1000.0,
        None if last_delivery is None else last_delivery * 1000.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("all", "lan", "regional", "adverse"),
        default="all",
    )
    parser.add_argument("--messages", type=int, default=200)
    parser.add_argument("--seed", type=int, default=53)
    args = parser.parse_args()
    profiles = {
        profile.name: profile
        for profile in net.REPRESENTATIVE_NETWORK_CONDITIONS
    }
    selected = (
        tuple(profiles.values())
        if args.profile == "all"
        else (profiles[args.profile],)
    )
    for profile in selected:
        result = simulate(profile, messages=args.messages, seed=args.seed)
        first = (
            "none"
            if result.first_delivery_ms is None
            else f"{result.first_delivery_ms:.1f}ms"
        )
        last = (
            "none"
            if result.last_delivery_ms is None
            else f"{result.last_delivery_ms:.1f}ms"
        )
        print(
            f"{result.profile:8} sent={result.sent} delivered={result.delivered} "
            f"lost={result.lost} first={first} last={last}"
        )


if __name__ == "__main__":
    main()
