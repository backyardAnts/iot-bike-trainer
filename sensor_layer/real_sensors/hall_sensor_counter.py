"""Production GrovePi Hall sensor counters for speed and cadence."""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, Optional, Tuple

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


MAX_SPEED_KMH = 80.0
MAX_CADENCE_RPM = 180


class HallSensorCounter(object):
    """Poll one Hall sensor and count debounced raw state changes."""

    def __init__(
        self,
        port: int,
        label: str,
        debounce_seconds: float = 0.25,
        magnets_per_rotation: int = 1,
        poll_interval_seconds: float = 0.05,
        timeout_seconds: float = 3.0,
        debug: bool = False,
    ) -> None:
        self.port = int(port)
        self.label = str(label)
        self.debounce_seconds = max(0.25, float(debounce_seconds))
        self.magnets_per_rotation = max(1, int(magnets_per_rotation))
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.debug = bool(debug)
        self.grovepi = load_grovepi()

        self._lock = threading.Lock()
        self._running = False
        self._thread = None  # type: Optional[threading.Thread]
        self._raw_value = None  # type: Optional[int]
        self._previous_raw_value = None  # type: Optional[int]
        self._event_count = 0
        self._last_event_time = None  # type: Optional[float]
        self._previous_event_time = None  # type: Optional[float]
        self._last_error = ""

        if self.grovepi is None:
            self._warn_once(
                "{} Hall sensor disabled: GrovePi import failed: {}".format(
                    self.label,
                    get_grovepi_error(),
                )
            )
            return

        try:
            self.grovepi.pinMode(self.port, "INPUT")
        except Exception as exc:
            self._warn_once(
                "{} D{} pinMode failed: {}".format(self.label, self.port, exc)
            )

        self.start()

    def start(self) -> None:
        """Start background polling."""
        if self.grovepi is None or self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop)
        self._thread.daemon = True
        self._thread.start()

    def stop(self) -> None:
        """Stop background polling."""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_measurement(self) -> Dict[str, Any]:
        """Return raw value, event count, rotations per second, and RPM."""
        with self._lock:
            raw_value = self._raw_value
            event_count = self._event_count
            last_event_time = self._last_event_time
            previous_event_time = self._previous_event_time

        now = time.monotonic()
        seconds_since_last_event = None  # type: Optional[float]
        if last_event_time is not None:
            seconds_since_last_event = now - last_event_time

        period_seconds = None  # type: Optional[float]
        if last_event_time is not None and previous_event_time is not None:
            period_seconds = last_event_time - previous_event_time

        events_per_second = 0.0
        if (
            period_seconds is not None
            and period_seconds > 0
            and seconds_since_last_event is not None
            and seconds_since_last_event <= self.timeout_seconds
        ):
            events_per_second = 1.0 / period_seconds

        rotations_per_second = events_per_second / self.magnets_per_rotation
        rpm = rotations_per_second * 60.0
        return {
            "raw_value": raw_value,
            "event_count": event_count,
            "last_event_time": last_event_time,
            "period_seconds": period_seconds,
            "seconds_since_last_event": seconds_since_last_event,
            "events_per_second": events_per_second,
            "rotations_per_second": rotations_per_second,
            "rpm": rpm,
        }

    def _poll_loop(self) -> None:
        while self._running:
            self.poll_once()
            time.sleep(self.poll_interval_seconds)

    def poll_once(self) -> None:
        """Read the digital input once and count state-change events."""
        if self.grovepi is None:
            return

        try:
            raw_value = int(self.grovepi.digitalRead(self.port))
        except Exception as exc:
            self._warn_once(
                "{} D{} read failed: {}".format(self.label, self.port, exc)
            )
            time.sleep(0.1)
            return

        now = time.monotonic()
        with self._lock:
            self._raw_value = raw_value
            if self._previous_raw_value is None:
                self._previous_raw_value = raw_value
                return

            if raw_value == self._previous_raw_value:
                return

            self._previous_raw_value = raw_value
            if (
                self._last_event_time is not None
                and now - self._last_event_time < self.debounce_seconds
            ):
                return

            self._previous_event_time = self._last_event_time
            self._last_event_time = now
            self._event_count += 1

    def _warn_once(self, message: str) -> None:
        if message == self._last_error:
            return
        self._last_error = message
        print(message)


class SpeedCadenceHallSensors(object):
    """Convert speed/cadence Hall events into km/h and RPM."""

    def __init__(
        self,
        speed_port: int = 3,
        cadence_port: int = 4,
        wheel_diameter_cm: float = 70.0,
        speed_magnets_per_rotation: int = 1,
        cadence_magnets_per_rotation: int = 1,
        debounce_seconds: float = 0.25,
        debug: bool = False,
    ) -> None:
        self.wheel_diameter_cm = float(wheel_diameter_cm)
        self.wheel_circumference_m = math.pi * (self.wheel_diameter_cm / 100.0)
        self.debug = bool(debug)
        self.speed_counter = HallSensorCounter(
            port=speed_port,
            label="Speed",
            debounce_seconds=debounce_seconds,
            magnets_per_rotation=speed_magnets_per_rotation,
            debug=debug,
        )
        self.cadence_counter = HallSensorCounter(
            port=cadence_port,
            label="Cadence",
            debounce_seconds=debounce_seconds,
            magnets_per_rotation=cadence_magnets_per_rotation,
            debug=debug,
        )
        self._speed_kmh = 0.0
        self._cadence_rpm = 0
        self._last_error = ""
        self._last_speed_measurement = self.speed_counter.get_measurement()
        self._last_cadence_measurement = self.cadence_counter.get_measurement()

    def read(self) -> Tuple[float, int]:
        """Return speed_kmh and cadence_rpm."""
        self._last_speed_measurement = self.speed_counter.get_measurement()
        self._last_cadence_measurement = self.cadence_counter.get_measurement()

        speed_rps = float(self._last_speed_measurement["rotations_per_second"])
        cadence_rpm = float(self._last_cadence_measurement["rpm"])
        self._speed_kmh = self._clean_speed_kmh(
            speed_rps * self.wheel_circumference_m * 3.6
        )
        self._cadence_rpm = self._clean_cadence_rpm(cadence_rpm)
        return self._speed_kmh, self._cadence_rpm

    def get_debug_text(self) -> str:
        """Return one-line raw/event debug text for terminal output."""
        speed_raw = self._format_raw(self._last_speed_measurement.get("raw_value"))
        cadence_raw = self._format_raw(self._last_cadence_measurement.get("raw_value"))
        return (
            "HALL DEBUG: SPEED D3 raw={speed_raw} events={speed_events} | "
            "CADENCE D4 raw={cadence_raw} events={cadence_events}"
        ).format(
            speed_raw=speed_raw,
            speed_events=self._last_speed_measurement.get("event_count", 0),
            cadence_raw=cadence_raw,
            cadence_events=self._last_cadence_measurement.get("event_count", 0),
        )

    def stop(self) -> None:
        """Stop both Hall sensor polling threads."""
        self.speed_counter.stop()
        self.cadence_counter.stop()

    def _format_raw(self, raw_value: Any) -> str:
        if raw_value is None:
            return "INVALID"
        return str(raw_value)

    def _clean_speed_kmh(self, value: float) -> float:
        speed_kmh = round(float(value), 2)
        if speed_kmh < 0:
            return 0.0
        if speed_kmh > MAX_SPEED_KMH:
            self._warn_once(
                "Hall speed ignored: {:.2f} km/h is above {}".format(
                    speed_kmh,
                    MAX_SPEED_KMH,
                )
            )
            return 0.0
        return speed_kmh

    def _clean_cadence_rpm(self, value: float) -> int:
        cadence_rpm = int(round(float(value)))
        if cadence_rpm < 0:
            return 0
        if cadence_rpm > MAX_CADENCE_RPM:
            self._warn_once(
                "Hall cadence ignored: {} rpm is above {}".format(
                    cadence_rpm,
                    MAX_CADENCE_RPM,
                )
            )
            return 0
        return cadence_rpm

    def _warn_once(self, message: str) -> None:
        if message == self._last_error:
            return
        self._last_error = message
        print(message)
