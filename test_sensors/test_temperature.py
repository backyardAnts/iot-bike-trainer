"""Simple GrovePi temperature and humidity sensor test for D2."""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Any, Optional, Tuple


DEFAULT_PORT = 2
DEFAULT_SENSOR_TYPE = 0
DEFAULT_INTERVAL_SECONDS = 1.0
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


def read_temperature_humidity(
    grovepi: Any,
    port: int,
    sensor_type: int,
) -> Tuple[Optional[float], Optional[float]]:
    """Read DHT temperature and humidity, returning None values when invalid."""
    try:
        temperature_c, humidity_percent = grovepi.dht(port, sensor_type)
    except Exception as exc:
        print("TEMP D{} read error: {}".format(port, exc))
        return None, None

    temperature_c = clean_number(temperature_c)
    humidity_percent = clean_number(humidity_percent)
    if temperature_c is None or humidity_percent is None:
        return None, None

    return temperature_c, humidity_percent


def clean_number(value: Any) -> Optional[float]:
    """Return a finite number, or None for invalid GrovePi values."""
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def main() -> None:
    parser = argparse.ArgumentParser(description="Test GrovePi DHT sensor.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sensor-type", type=int, default=DEFAULT_SENSOR_TYPE)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()

    grovepi = import_grovepi()
    print("Testing GrovePi temperature/humidity sensor. Press Ctrl+C to stop.")

    try:
        while True:
            temperature_c, humidity_percent = read_temperature_humidity(
                grovepi,
                args.port,
                args.sensor_type,
            )

            if temperature_c is None or humidity_percent is None:
                print("TEMP D{}: INVALID".format(args.port))
            else:
                print(
                    "TEMP D{}: {:.1f} °C | HUMIDITY: {:.1f} %".format(
                        args.port,
                        temperature_c,
                        humidity_percent,
                    )
                )

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped temperature test.")


if __name__ == "__main__":
    main()
