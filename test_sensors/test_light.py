"""Simple GrovePi light or LED blink test for D7.

Use this to verify a simple digital output before connecting it to the full
bike feedback flow.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any


DEFAULT_PORT = 7
DEFAULT_ON_TIME_SECONDS = 1.0
DEFAULT_OFF_TIME_SECONDS = 1.0
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


def safe_pin_mode(grovepi: Any, port: int, mode: str) -> None:
    """Set pin mode without crashing the script."""
    try:
        grovepi.pinMode(port, mode)
    except Exception as exc:
        print("LIGHT D{} pinMode error: {}".format(port, exc))


def safe_write(grovepi: Any, port: int, value: int) -> bool:
    """Write a digital value and return whether it succeeded."""
    try:
        grovepi.digitalWrite(port, value)
        return True
    except Exception as exc:
        print("LIGHT D{} write error: {}".format(port, exc))
        return False


def main() -> None:
    """Blink the configured output port until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Blink GrovePi light/LED.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--on-time", type=float, default=DEFAULT_ON_TIME_SECONDS)
    parser.add_argument("--off-time", type=float, default=DEFAULT_OFF_TIME_SECONDS)
    args = parser.parse_args()

    grovepi = import_grovepi()
    safe_pin_mode(grovepi, args.port, "OUTPUT")
    print("Testing GrovePi light/LED. Press Ctrl+C to stop.")

    try:
        while True:
            # A visible blink confirms the port can be written high and low.
            if safe_write(grovepi, args.port, 1):
                print("LIGHT D{}: ON".format(args.port))
            time.sleep(args.on_time)

            if safe_write(grovepi, args.port, 0):
                print("LIGHT D{}: OFF".format(args.port))
            time.sleep(args.off_time)
    except KeyboardInterrupt:
        print("\nStopping light test.")
    finally:
        # Leave the output low after the test stops.
        safe_write(grovepi, args.port, 0)
        print("LIGHT D{}: OFF".format(args.port))


if __name__ == "__main__":
    main()
