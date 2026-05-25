"""Simple GrovePi ultrasonic sensor test for D5 and D6."""

from __future__ import annotations

import sys
import time
from typing import Any, Optional


LEFT_PORT = 5
RIGHT_PORT = 6
READ_INTERVAL_SECONDS = 0.5
GROVEPI_PATHS = (
    "/home/pi/Dexter/GrovePi/Software/Python",
    "/home/pi/Dexter/GrovePi/Software/Python/grovepi",
)


def import_grovepi() -> Any:
    """Import grovepi, adding common Raspberry Pi paths if needed."""
    try:
        import grovepi

        return grovepi
    except ImportError:
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


def read_distance_cm(grovepi: Any, port: int) -> Optional[int]:
    """Read one ultrasonic sensor and return valid centimeters, or None."""
    try:
        value = grovepi.ultrasonicRead(port)
    except Exception:
        return None

    return clean_distance_cm(value)


def clean_distance_cm(value: Any) -> Optional[int]:
    """Return an integer centimeter value, or None for invalid readings."""
    if value is None:
        return None

    try:
        distance_cm = int(value)
    except (TypeError, ValueError):
        return None

    if distance_cm <= 0:
        return None
    if distance_cm == 65535:
        return None
    if distance_cm > 400:
        return None

    return distance_cm


def format_reading(label: str, port: int, distance_cm: Optional[int]) -> str:
    """Format one terminal output line."""
    if distance_cm is None:
        return "{} D{}: INVALID".format(label, port)

    distance_m = distance_cm / 100.0
    return "{} D{}: {} cm / {:.2f} m".format(
        label,
        port,
        distance_cm,
        distance_m,
    )


def main() -> None:
    grovepi = import_grovepi()
    print("Testing GrovePi ultrasonic sensors. Press Ctrl+C to stop.")

    try:
        while True:
            left_cm = read_distance_cm(grovepi, LEFT_PORT)
            right_cm = read_distance_cm(grovepi, RIGHT_PORT)

            print(format_reading("LEFT", LEFT_PORT, left_cm))
            print(format_reading("RIGHT", RIGHT_PORT, right_cm))
            time.sleep(READ_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped ultrasonic test.")


if __name__ == "__main__":
    main()
