"""Run the Phase 3 virtual bike sensor simulator."""

from __future__ import annotations

import argparse
import time

from common.message_schema import message_to_json, validate_sensor_message
from config_layer.settings import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_SAMPLE_INTERVAL_SECONDS,
)
from sensor_layer.virtual_sensors.virtual_bike import VirtualBike


def run_forever(random_seed: int | None = DEFAULT_RANDOM_SEED) -> None:
    """Print one JSON sensor message per sample interval until Ctrl+C."""
    bike = VirtualBike(random_seed=random_seed)
    print("Virtual bike simulator started. Press Ctrl+C to stop.")

    try:
        while True:
            message = bike.update()
            print(message_to_json(message), flush=True)
            time.sleep(DEFAULT_SAMPLE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nVirtual bike simulator stopped.")


def run_self_test(reading_count: int = 10) -> None:
    """Run a short deterministic simulation and validate each message."""
    bike = VirtualBike(random_seed=42)
    print(f"Running virtual bike self-test for {reading_count} readings.")

    for _ in range(reading_count):
        message = bike.update()
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")
        print(message_to_json(message))

    print("Self-test passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 3 virtual bike simulator")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="print 10 readings and validate the output schema",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="optional random seed for repeatable virtual readings",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        run_self_test()
    else:
        run_forever(random_seed=args.seed)

