"""Production GrovePi Hall sensor event counters for speed and cadence."""

from __future__ import annotations

import threading
import time
from typing import Optional

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


class HallSensorCounter(object):
    """Poll one Hall sensor and count debounced raw state changes."""

    def __init__(
        self,
        label: str,
        port: int,
        debounce_seconds: float = 0.08,
        poll_interval_seconds: float = 0.02,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.label = str(label)
        self.port = int(port)
        self.debounce_seconds = float(debounce_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.grovepi = load_grovepi()

        self._lock = threading.Lock()
        self._running = False
        self._thread = None  # type: Optional[threading.Thread]
        self._previous_raw = None  # type: Optional[int]
        self._last_event_time = None  # type: Optional[float]
        self._previous_event_time = None  # type: Optional[float]
        self._last_poll_error = ""
        self._event_count = 0

        if self.grovepi is None:
            self._warn(
                "{} Hall sensor disabled: GrovePi import failed: {}".format(
                    self.label,
                    get_grovepi_error(),
                )
            )
            return

        try:
            self.grovepi.pinMode(self.port, "INPUT")
        except Exception as exc:
            self._warn(
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

    def get_event_count(self) -> int:
        """Return total debounced state-change events."""
        with self._lock:
            return self._event_count

    def get_latest_period_seconds(self) -> Optional[float]:
        """Return seconds between the latest two valid events."""
        with self._lock:
            if self._last_event_time is None or self._previous_event_time is None:
                return None
            return self._last_event_time - self._previous_event_time

    def get_seconds_since_last_event(self) -> Optional[float]:
        """Return seconds since the last event, or None if no event happened."""
        with self._lock:
            if self._last_event_time is None:
                return None
            return time.monotonic() - self._last_event_time

    def _poll_loop(self) -> None:
        while self._running:
            self.poll_once()
            time.sleep(self.poll_interval_seconds)

    def poll_once(self) -> None:
        """Poll the digital input once and count a state-change event."""
        if self.grovepi is None:
            return

        try:
            raw_value = int(self.grovepi.digitalRead(self.port))
        except Exception as exc:
            self._warn(
                "{} D{} read failed: {}".format(self.label, self.port, exc)
            )
            time.sleep(0.1)
            return

        now = time.monotonic()
        with self._lock:
            if self._previous_raw is None:
                self._previous_raw = raw_value
                return

            if raw_value == self._previous_raw:
                return

            if (
                self._last_event_time is not None
                and now - self._last_event_time < self.debounce_seconds
            ):
                self._previous_raw = raw_value
                return

            self._previous_raw = raw_value
            self._previous_event_time = self._last_event_time
            self._last_event_time = now
            self._event_count += 1

    def _warn(self, message: str) -> None:
        if message == self._last_poll_error:
            return
        self._last_poll_error = message
        print(message)


class SpeedCadenceHallSensors(object):
    """Convert Hall state-change events into speed and cadence estimates."""

    def __init__(
        self,
        speed_port: int = 3,
        cadence_port: int = 4,
        wheel_circumference_m: float = 2.10,
    ) -> None:
        self.speed_counter = HallSensorCounter("Speed", speed_port)
        self.cadence_counter = HallSensorCounter("Cadence", cadence_port)
        self.wheel_circumference_m = float(wheel_circumference_m)
        self._speed_kmh = 0.0
        self._cadence_rpm = 0.0

    def read_speed_kmh(self) -> float:
        """Return a smoothed speed estimate in km/h."""
        period_seconds = self.speed_counter.get_latest_period_seconds()
        seconds_since_event = self.speed_counter.get_seconds_since_last_event()

        if period_seconds is not None and period_seconds > 0:
            rotations_per_second = 1.0 / period_seconds
            instant_speed_kmh = (
                rotations_per_second * self.wheel_circumference_m * 3.6
            )
            self._speed_kmh = self._smooth(self._speed_kmh, instant_speed_kmh)

        self._speed_kmh = self._decay_toward_zero(
            self._speed_kmh,
            seconds_since_event,
            self.speed_counter.timeout_seconds,
        )
        return self._speed_kmh

    def read_cadence_rpm(self) -> int:
        """Return a smoothed cadence estimate in RPM."""
        period_seconds = self.cadence_counter.get_latest_period_seconds()
        seconds_since_event = self.cadence_counter.get_seconds_since_last_event()

        if period_seconds is not None and period_seconds > 0:
            instant_cadence_rpm = 60.0 / period_seconds
            self._cadence_rpm = self._smooth(self._cadence_rpm, instant_cadence_rpm)

        self._cadence_rpm = self._decay_toward_zero(
            self._cadence_rpm,
            seconds_since_event,
            self.cadence_counter.timeout_seconds,
        )
        return int(round(self._cadence_rpm))

    def get_event_counts(self) -> tuple:
        """Return speed and cadence event totals."""
        return (
            self.speed_counter.get_event_count(),
            self.cadence_counter.get_event_count(),
        )

    def stop(self) -> None:
        """Stop both Hall sensor polling threads."""
        self.speed_counter.stop()
        self.cadence_counter.stop()

    def _smooth(self, current_value: float, new_value: float) -> float:
        if current_value <= 0:
            return new_value
        return (current_value * 0.65) + (new_value * 0.35)

    def _decay_toward_zero(
        self,
        value: float,
        seconds_since_event: Optional[float],
        timeout_seconds: float,
    ) -> float:
        if seconds_since_event is None:
            return 0.0
        if seconds_since_event <= timeout_seconds:
            return value

        decayed = value * 0.7
        if decayed < 0.5:
            return 0.0
        return decayed
