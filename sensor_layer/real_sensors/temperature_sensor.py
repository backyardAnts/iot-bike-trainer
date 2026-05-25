"""Production GrovePi temperature and humidity sensor wrapper."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


class TemperatureSensor(object):
    """Read temperature and humidity from a Grove DHT sensor."""

    def __init__(
        self,
        port: int = 2,
        sensor_type: int = 0,
        fallback_temperature_c: float = 25.0,
    ) -> None:
        self.port = int(port)
        self.sensor_type = int(sensor_type)
        self.fallback_temperature_c = float(fallback_temperature_c)
        self.grovepi = load_grovepi()
        self._warned_missing = False
        self._last_error = ""

        if self.grovepi is None:
            self._warn_once(
                "Temperature sensor disabled: GrovePi import failed: {}".format(
                    get_grovepi_error()
                )
            )

    def read(self) -> Dict[str, Optional[float]]:
        """Return temperature_c and humidity_percent with safe fallbacks."""
        if self.grovepi is None:
            return self._fallback()

        try:
            temperature_c, humidity_percent = self.grovepi.dht(
                self.port,
                self.sensor_type,
            )
        except Exception as exc:
            self._warn_once("Temperature D{} read failed: {}".format(self.port, exc))
            return self._fallback()

        temperature_c = self._clean_number(temperature_c)
        humidity_percent = self._clean_number(humidity_percent)
        if temperature_c is None:
            return self._fallback()

        return {
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
        }

    def _fallback(self) -> Dict[str, Optional[float]]:
        return {
            "temperature_c": self.fallback_temperature_c,
            "humidity_percent": None,
        }

    def _clean_number(self, value: Any) -> Optional[float]:
        if value is None:
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    def _warn_once(self, message: str) -> None:
        if message == self._last_error:
            return
        self._last_error = message
        print(message)
