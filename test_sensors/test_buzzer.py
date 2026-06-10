"""Simple GrovePi buzzer test for D7.

Use this script before running the full bike loop to make sure the buzzer is
wired to the expected digital port.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any


DEFAULT_PORT = 7
DEFAULT_ON_TIME_SECONDS = 0.5
DEFAULT_OFF_TIME_SECONDS = 0.5
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
    """Set pin mode without stopping the script."""
    try:
        grovepi.pinMode(port, mode)
    except Exception as exc:
        print("BUZZER D{} pinMode error: {}".format(port, exc))


def safe_write(grovepi: Any, port: int, value: int) -> bool:
    """Write a digital value and return whether it succeeded."""
    try:
        grovepi.digitalWrite(port, value)
        return True
    except Exception as exc:
        print("BUZZER D{} write error: {}".format(port, exc))
        return False


def main() -> None:
    """Blink the buzzer on and off until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Test GrovePi buzzer.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--on-time", type=float, default=DEFAULT_ON_TIME_SECONDS)
    parser.add_argument("--off-time", type=float, default=DEFAULT_OFF_TIME_SECONDS)
    args = parser.parse_args()

    grovepi = import_grovepi()
    safe_pin_mode(grovepi, args.port, "OUTPUT")
    print("Testing GrovePi buzzer. Press Ctrl+C to stop.")

    try:
        while True:
            # The loop is simple on purpose: if it toggles, the wiring works.
            if safe_write(grovepi, args.port, 1):
                print("BUZZER D{}: ON".format(args.port))
            time.sleep(args.on_time)

            if safe_write(grovepi, args.port, 0):
                print("BUZZER D{}: OFF".format(args.port))
            time.sleep(args.off_time)
    except KeyboardInterrupt:
        print("\nStopping buzzer test.")
    finally:
        # Leave the buzzer off even if the user stops during the ON half-cycle.
        safe_write(grovepi, args.port, 0)
        print("BUZZER D{}: OFF".format(args.port))


if __name__ == "__main__":
    main()
