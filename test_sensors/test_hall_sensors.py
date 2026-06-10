"""Simple GrovePi Hall effect sensor test for D3 and D4.

This only checks raw state changes, which is the fastest way to prove the
magnet and Hall module are wired correctly.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Optional


DEFAULT_SPEED_PORT = 3
DEFAULT_CADENCE_PORT = 4
DEFAULT_INTERVAL_SECONDS = 0.2
GROVEPI_PATHS = (
    # Common GrovePi install paths on the Raspberry Pi image.
    "/home/pi/Dexter/GrovePi/Software/Python",
    "/home/pi/Dexter/GrovePi/Software/Python/grovepi",
)


def import_grovepi() -> Any:
    """Import grovepi, adding common Raspberry Pi paths if needed."""
    try:
        import grovepi

        return grovepi
    except ImportError:
        # Try the paths used by the standard Dexter GrovePi installation.
        for path in GROVEPI_PATHS:
            if path not in sys.path:
                sys.path.append(path)

    try:
        import grovepi

        return grovepi
    except ImportError as exc:
        print("Could not import grovepi.")
        print("Checked normal import and these paths:")
        for path in GROVEPI_PATHS:
            print("  " + path)
        raise SystemExit(1) from exc


def safe_pin_mode(grovepi: Any, port: int, mode: str, label: str) -> None:
    """Set pin mode without crashing the script."""
    try:
        grovepi.pinMode(port, mode)
    except Exception as exc:
        print("{} D{} pinMode error: {}".format(label, port, exc))


def read_raw_state(grovepi: Any, port: int, label: str) -> Optional[int]:
    """Read one digital input and return 0, 1, or None on error."""
    try:
        return int(grovepi.digitalRead(port))
    except Exception as exc:
        print("{} D{} read error: {}".format(label, port, exc))
        return None


def print_state(label: str, port: int, raw_value: Optional[int], events: int) -> None:
    """Print the current raw sensor state."""
    if raw_value is None:
        print("{} D{}: raw=INVALID | events={}".format(label, port, events))
    else:
        print("{} D{}: raw={} | events={}".format(label, port, raw_value, events))


def print_event(label: str, port: int, total: int) -> None:
    """Print a magnet event message."""
    print("{} D{}: MAGNET EVENT detected | total={}".format(label, port, total))


def main() -> None:
    """Print raw Hall states and count every state change."""
    parser = argparse.ArgumentParser(description="Test GrovePi Hall sensors.")
    parser.add_argument("--speed-port", type=int, default=DEFAULT_SPEED_PORT)
    parser.add_argument("--cadence-port", type=int, default=DEFAULT_CADENCE_PORT)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()

    grovepi = import_grovepi()
    safe_pin_mode(grovepi, args.speed_port, "INPUT", "SPEED")
    safe_pin_mode(grovepi, args.cadence_port, "INPUT", "CADENCE")

    speed_events = 0
    cadence_events = 0
    previous_speed_raw = None
    previous_cadence_raw = None

    print("Testing GrovePi Hall effect sensors. Press Ctrl+C to stop.")
    print("Move a magnet near each Hall sensor. If raw value changes, the sensor works.")

    try:
        while True:
            speed_raw = read_raw_state(grovepi, args.speed_port, "SPEED")
            cadence_raw = read_raw_state(grovepi, args.cadence_port, "CADENCE")

            # Any raw-value change means the magnet affected the sensor.
            if (
                previous_speed_raw is not None
                and speed_raw is not None
                and speed_raw != previous_speed_raw
            ):
                speed_events += 1
                print_event("SPEED", args.speed_port, speed_events)

            if (
                previous_cadence_raw is not None
                and cadence_raw is not None
                and cadence_raw != previous_cadence_raw
            ):
                cadence_events += 1
                print_event("CADENCE", args.cadence_port, cadence_events)

            print_state("SPEED", args.speed_port, speed_raw, speed_events)
            print_state("CADENCE", args.cadence_port, cadence_raw, cadence_events)

            if speed_raw is not None:
                # Do not overwrite the previous good value with a failed read.
                previous_speed_raw = speed_raw
            if cadence_raw is not None:
                previous_cadence_raw = cadence_raw

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped Hall sensor test.")
        print("Speed events: {}".format(speed_events))
        print("Cadence events: {}".format(cadence_events))


if __name__ == "__main__":
    main()
