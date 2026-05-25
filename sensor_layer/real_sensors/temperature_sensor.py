"""Production GrovePi temperature and humidity sensor wrapper."""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


class TemperatureSensor(object):
    """Read temperature and humidity from a Grove DHT sensor."""

    def __init__(
        self,
        port: int = 2,
        sensor_type: int = 0,
        fallback_temperature_c: float = 25.0,
        min_read_interval_seconds: float = 2.0,
        debug: bool = False,
    ) -> None:
        self.port = int(port)
        self.sensor_type = int(sensor_type)
        self.fallback_temperature_c = float(fallback_temperature_c)
        self.min_read_interval_seconds = float(min_read_interval_seconds)
        self.debug = bool(debug)
        self.grovepi = load_grovepi()
        self._warned_missing = False
        self._last_error = ""
        self._last_warning_time = 0.0
        self._last_read_time = 0.0
        self._last_temperature_c = None  # type: Optional[float]
        self._last_humidity_percent = None  # type: Optional[float]

        if self.grovepi is None:
            self._warn_once(
                "Temperature sensor disabled: GrovePi import failed: {}".format(
                    get_grovepi_error()
                )
            )

    def read(self) -> Dict[str, Optional[float]]:
        """Return temperature_c and humidity_percent with safe fallbacks."""
        now = time.monotonic()
        if now - self._last_read_time < self.min_read_interval_seconds:
            if self._last_temperature_c is not None:
                return self._reading_from_cache(fallback_used=False)
            return self._fallback(fallback_used=False)

        if self.grovepi is None:
            return self._fallback(fallback_used=True)

        self._last_read_time = now
        try:
            raw_temperature_c, raw_humidity_percent = self.grovepi.dht(
                self.port,
                self.sensor_type,
            )
        except Exception as exc:
            self._warn_occasionally(
                "Temperature D{} read failed: {}".format(self.port, exc)
            )
            return self._fallback(fallback_used=True)

        temperature_c = self._clean_temperature_c(raw_temperature_c)
        humidity_percent = self._clean_humidity_percent(raw_humidity_percent)
        if self.debug:
            print(
                "TEMP DEBUG: D{} sensor_type={} raw_temp={} raw_humidity={} fallback={}".format(
                    self.port,
                    self.sensor_type,
                    raw_temperature_c,
                    raw_humidity_percent,
                    temperature_c is None,
                )
            )
        if temperature_c is None:
            self._warn_occasionally(
                "Temperature D{} invalid reading: temp={} humidity={}".format(
                    self.port,
                    raw_temperature_c,
                    raw_humidity_percent,
                )
            )
            return self._fallback(fallback_used=True)

        self._last_temperature_c = temperature_c
        self._last_humidity_percent = humidity_percent
        return {
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
        }

    def _fallback(self, fallback_used: bool) -> Dict[str, Optional[float]]:
        if self._last_temperature_c is not None:
            if self.debug:
                print(
                    "TEMP DEBUG: D{} sensor_type={} using cached temperature fallback={}".format(
                        self.port,
                        self.sensor_type,
                        fallback_used,
                    )
                )
            return self._reading_from_cache(fallback_used=fallback_used)

        if self.debug:
            print(
                "TEMP DEBUG: D{} sensor_type={} using default temperature fallback={}".format(
                    self.port,
                    self.sensor_type,
                    fallback_used,
                )
            )
        return {
            "temperature_c": self.fallback_temperature_c,
            "humidity_percent": None,
        }

    def _reading_from_cache(self, fallback_used: bool) -> Dict[str, Optional[float]]:
        if self.debug:
            print(
                "TEMP DEBUG: D{} sensor_type={} cached_temp={} cached_humidity={} fallback={}".format(
                    self.port,
                    self.sensor_type,
                    self._last_temperature_c,
                    self._last_humidity_percent,
                    fallback_used,
                )
            )
        return {
            "temperature_c": self._last_temperature_c,
            "humidity_percent": self._last_humidity_percent,
        }

    def _clean_temperature_c(self, value: Any) -> Optional[float]:
        number = self._clean_number(value)
        if number is None:
            return None
        if number < -40.0 or number > 80.0:
            return None
        return number

    def _clean_humidity_percent(self, value: Any) -> Optional[float]:
        number = self._clean_number(value)
        if number is None:
            return None
        if number < 0.0 or number > 100.0:
            return None
        return number

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

    def _warn_occasionally(self, message: str) -> None:
        now = time.monotonic()
        if message == self._last_error and now - self._last_warning_time < 10.0:
            return
        self._last_error = message
        self._last_warning_time = now
        print(message)
