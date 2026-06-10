"""Production GrovePi ultrasonic side-distance sensors.

The bike uses two ultrasonic sensors for left/right clearance, returning a
safe fallback distance when the hardware reading is invalid.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


class UltrasonicSensors(object):
    """Read left and right Grove ultrasonic sensors in meters."""

    def __init__(
        self,
        left_port: int = 5,
        right_port: int = 6,
        fallback_distance_m: float = 9.99,
        between_read_delay_seconds: float = 0.06,
    ) -> None:
        """Configure the two ultrasonic ports and fallback distance."""
        self.left_port = int(left_port)
        self.right_port = int(right_port)
        self.fallback_distance_m = float(fallback_distance_m)
        self.between_read_delay_seconds = float(between_read_delay_seconds)
        self.grovepi = load_grovepi()
        self._last_left_m = None  # type: Optional[float]
        self._last_right_m = None  # type: Optional[float]
        self._last_errors = {}  # type: dict
        self._last_status = {
            "left_valid": False,
            "right_valid": False,
            "left_raw_cm": None,
            "right_raw_cm": None,
        }  # type: Dict[str, Any]

        if self.grovepi is None:
            self._warn_once(
                "both",
                "Ultrasonic sensors disabled: GrovePi import failed: {}".format(
                    get_grovepi_error()
                ),
            )

    def read(self) -> Tuple[float, float]:
        """Return left_distance_m and right_distance_m."""
        # Reading the sensors with a tiny gap reduces cross-talk between pings.
        left_result = self._read_one(
            "left",
            self.left_port,
        )
        left_distance_m = left_result["distance_m"]
        self._last_left_m = left_distance_m

        time.sleep(self.between_read_delay_seconds)

        right_result = self._read_one(
            "right",
            self.right_port,
        )
        right_distance_m = right_result["distance_m"]
        self._last_right_m = right_distance_m
        self._last_status = {
            "left_valid": left_result["valid"],
            "right_valid": right_result["valid"],
            "left_raw_cm": left_result["raw_cm"],
            "right_raw_cm": right_result["raw_cm"],
        }

        return left_distance_m, right_distance_m

    def get_last_status(self) -> Dict[str, Any]:
        """Return validity and raw cm information from the latest read."""
        return dict(self._last_status)

    def _read_one(
        self,
        side: str,
        port: int,
    ) -> Dict[str, Any]:
        """Read one ultrasonic sensor and normalize it to meters."""
        if self.grovepi is None:
            return self._invalid_result()

        try:
            raw_cm = self.grovepi.ultrasonicRead(port)
        except Exception as exc:
            self._warn_once(
                side,
                "Ultrasonic {} D{} read failed: {}".format(side, port, exc),
            )
            return self._invalid_result(raw_cm=None)

        clean_cm = self._clean_distance_cm(raw_cm)
        if clean_cm is None:
            return self._invalid_result(raw_cm=raw_cm)

        return {
            "distance_m": clean_cm / 100.0,
            "valid": True,
            "raw_cm": clean_cm,
        }

    def _clean_distance_cm(self, value: Any) -> Optional[float]:
        """Accept only plausible Grove ultrasonic centimeter values."""
        if value is None:
            return None

        try:
            distance_cm = float(value)
        except (TypeError, ValueError):
            return None

        if distance_cm <= 0:
            return None
        if distance_cm == 65535:
            return None
        if distance_cm < 2:
            return None
        if distance_cm > 400:
            return None

        return distance_cm

    def _invalid_result(self, raw_cm: Any = None) -> Dict[str, Any]:
        """Return the safe fallback reading for one failed side."""
        return {
            "distance_m": self.fallback_distance_m,
            "valid": False,
            "raw_cm": raw_cm,
        }

    def _warn_once(self, key: str, message: str) -> None:
        """Print each side's warning once."""
        if self._last_errors.get(key) == message:
            return
        self._last_errors[key] = message
        print(message)
