"""Production GrovePi Hall sensor counters for speed and cadence.

Hall sensors produce digital pulses when a magnet passes. This module debounces
those pulses and converts full rotations into speed and cadence.
"""

from __future__ import annotations

from collections import deque
import math
import threading
import time
from typing import Any, Dict, Optional, Tuple

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


MAX_SPEED_KMH = 80.0
MAX_CADENCE_RPM = 180
POLL_DELAY_SECONDS = 0.001
DEBOUNCE_SECONDS = 0.04
STOP_TIMEOUT_SECONDS = 3.0
AVERAGE_WINDOW = 10
PULSES_PER_REVOLUTION = 2
MAGNET_DETECTED_STATE = 0
SUSPICIOUS_INTERVAL_FACTOR = 2.2


class HallSensorCounter(object):
    """Poll one Hall sensor and measure debounced magnet pulse intervals."""

    def __init__(
        self,
        port: int,
        label: str,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        magnets_per_rotation: int = PULSES_PER_REVOLUTION,
        poll_interval_seconds: float = POLL_DELAY_SECONDS,
        timeout_seconds: float = STOP_TIMEOUT_SECONDS,
        average_window: int = AVERAGE_WINDOW,
        magnet_detected_state: int = MAGNET_DETECTED_STATE,
        debug: bool = False,
        auto_start: bool = False,
    ) -> None:
        """Set up one Hall sensor counter and optional background polling."""
        self.port = int(port)
        self.label = str(label)
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self.magnets_per_rotation = max(1, int(magnets_per_rotation))
        self.poll_interval_seconds = max(0.001, float(poll_interval_seconds))
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.average_window = max(1, int(average_window))
        self.magnet_detected_state = int(magnet_detected_state)
        self.debug = bool(debug)
        self.auto_start = bool(auto_start)
        self.grovepi = load_grovepi()

        self._lock = threading.Lock()
        self._running = False
        self._thread = None  # type: Optional[threading.Thread]
        self._raw_value = None  # type: Optional[int]
        self._previous_raw_value = None  # type: Optional[int]
        self._event_count = 0
        self._last_event_time = None  # type: Optional[float]
        self._previous_event_time = None  # type: Optional[float]

        # Stores full-rotation periods, not only adjacent magnet-to-magnet periods.
        self._last_period_seconds = None  # type: Optional[float]
        self._period_samples = deque(maxlen=self.average_window)

        # Stores recent pulse timestamps so we can calculate full rotations.
        # Example with 2 magnets:
        # pulse 3 - pulse 1 = one full wheel rotation
        # pulse 4 - pulse 2 = one full wheel rotation
        self._pulse_timestamps = deque(maxlen=max(2, self.magnets_per_rotation + 1))

        self._consecutive_suspicious_intervals = 0
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

        if self.auto_start:
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
            last_period_seconds = self._last_period_seconds
            period_samples = tuple(self._period_samples)

        now = time.monotonic()
        seconds_since_last_event = None  # type: Optional[float]
        if last_event_time is not None:
            seconds_since_last_event = now - last_event_time

        stopped = (
            seconds_since_last_event is not None
            and seconds_since_last_event > self.timeout_seconds
        )

        average_period_seconds = None  # type: Optional[float]
        rotations_per_second = 0.0

        if period_samples and not stopped:
            average_period_seconds = sum(period_samples) / len(period_samples)
            if average_period_seconds > 0:
                rotations_per_second = 1.0 / average_period_seconds

        events_per_second = rotations_per_second * self.magnets_per_rotation
        rpm = rotations_per_second * 60.0

        return {
            "raw_value": raw_value,
            "event_count": event_count,
            "last_event_time": last_event_time,
            "previous_event_time": previous_event_time,
            "period_seconds": last_period_seconds,
            "average_period_seconds": average_period_seconds,
            "seconds_since_last_event": seconds_since_last_event,
            "events_per_second": events_per_second,
            "rotations_per_second": rotations_per_second,
            "rpm": rpm,
            "sample_count": len(period_samples),
        }

    def _poll_loop(self) -> None:
        """Poll continuously while the background thread is running."""
        while self._running:
            self.poll_once()
            time.sleep(self.poll_interval_seconds)

    def poll_once(self) -> None:
        """Read the digital input once and count magnet-detected pulse edges."""
        if self.grovepi is None:
            return

        try:
            raw_value = int(self.grovepi.digitalRead(self.port))
        except Exception as exc:
            self._warn_once("{} D{} read failed: {}".format(self.label, self.port, exc))
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

            previous_raw_value = self._previous_raw_value
            self._previous_raw_value = raw_value

            # Count only the edge where the magnet becomes detected.
            if (
                previous_raw_value == self.magnet_detected_state
                or raw_value != self.magnet_detected_state
            ):
                return

            self._record_pulse(now)

    def _record_pulse(self, now: float) -> None:
        """Debounce and store one accepted magnet pulse."""
        if (
            self._last_event_time is not None
            and now - self._last_event_time < self.debounce_seconds
        ):
            return

        if (
            self._last_event_time is not None
            and now - self._last_event_time > self.timeout_seconds
        ):
            # A long gap means the wheel probably stopped; old periods no longer help.
            self._period_samples.clear()
            self._pulse_timestamps.clear()
            self._consecutive_suspicious_intervals = 0

        full_rotation_period_seconds = self._calculate_full_rotation_period(now)

        effective_period_seconds = self._effective_period_seconds(
            full_rotation_period_seconds
        )
        if effective_period_seconds is not None:
            self._period_samples.append(effective_period_seconds)
            self._last_period_seconds = effective_period_seconds

        self._pulse_timestamps.append(now)
        self._previous_event_time = self._last_event_time
        self._last_event_time = now
        self._event_count += 1

    def _calculate_full_rotation_period(self, now: float) -> Optional[float]:
        """Calculate one full rotation period.

        With 1 magnet:
            current pulse - previous pulse = one rotation

        With 2 magnets:
            current pulse - pulse from 2 pulses ago = one rotation

        This is more stable than adjacent pulse timing because it reduces the
        effect of magnets not being perfectly 180 degrees apart.
        """
        if self.magnets_per_rotation <= 1:
            if self._last_event_time is None:
                return None
            return now - self._last_event_time

        if len(self._pulse_timestamps) < self.magnets_per_rotation:
            return None

        matching_previous_pulse_time = self._pulse_timestamps[
            -self.magnets_per_rotation
        ]
        return now - matching_previous_pulse_time

    def _effective_period_seconds(
        self,
        period_seconds: Optional[float],
    ) -> Optional[float]:
        """Correct one suspicious long interval before accepting a real slowdown."""
        if period_seconds is None or period_seconds <= 0:
            return None

        if period_seconds > self.timeout_seconds:
            self._period_samples.clear()
            self._consecutive_suspicious_intervals = 0
            return None

        if not self._period_samples:
            self._consecutive_suspicious_intervals = 0
            return period_seconds

        average_period_seconds = sum(self._period_samples) / len(self._period_samples)
        if average_period_seconds <= 0:
            self._consecutive_suspicious_intervals = 0
            return period_seconds

        if period_seconds < average_period_seconds * SUSPICIOUS_INTERVAL_FACTOR:
            self._consecutive_suspicious_intervals = 0
            return period_seconds

        missed_rotation_count = int(round(period_seconds / average_period_seconds))
        if missed_rotation_count < 2:
            self._consecutive_suspicious_intervals = 0
            return period_seconds

        self._consecutive_suspicious_intervals += 1

        if self._consecutive_suspicious_intervals == 1:
            # One long gap is usually a missed magnet edge, so divide it down.
            corrected_period_seconds = period_seconds / missed_rotation_count
            if self.debug:
                print(
                    "{} D{} suspicious rotation interval {:.3f}s corrected to {:.3f}s".format(
                        self.label,
                        self.port,
                        period_seconds,
                        corrected_period_seconds,
                    )
                )
            return corrected_period_seconds

        self._period_samples.clear()
        self._consecutive_suspicious_intervals = 0
        return period_seconds

    def _warn_once(self, message: str) -> None:
        """Print each hardware warning once."""
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
        speed_magnets_per_rotation: int = PULSES_PER_REVOLUTION,
        cadence_magnets_per_rotation: int = 1,
        debounce_seconds: float = DEBOUNCE_SECONDS,
        poll_interval_seconds: float = POLL_DELAY_SECONDS,
        timeout_seconds: float = STOP_TIMEOUT_SECONDS,
        average_window: int = AVERAGE_WINDOW,
        debug: bool = False,
        background_polling: bool = False,
    ) -> None:
        """Create paired counters and wheel math for speed/cadence."""
        self.wheel_diameter_cm = float(wheel_diameter_cm)
        self.wheel_circumference_m = math.pi * (self.wheel_diameter_cm / 100.0)
        self.debug = bool(debug)

        self.speed_counter = HallSensorCounter(
            port=speed_port,
            label="Speed",
            debounce_seconds=debounce_seconds,
            magnets_per_rotation=speed_magnets_per_rotation,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            average_window=average_window,
            debug=debug,
            auto_start=background_polling,
        )

        self.cadence_counter = HallSensorCounter(
            port=cadence_port,
            label="Cadence",
            debounce_seconds=debounce_seconds,
            magnets_per_rotation=cadence_magnets_per_rotation,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            average_window=average_window,
            debug=debug,
            auto_start=background_polling,
        )

        self._speed_kmh = 0.0
        self._cadence_rpm = 0
        self._last_error = ""
        self._last_speed_measurement = self.speed_counter.get_measurement()
        self._last_cadence_measurement = self.cadence_counter.get_measurement()

    def poll_once(self) -> None:
        """Poll both Hall inputs once without using background threads."""
        self.speed_counter.poll_once()
        self.cadence_counter.poll_once()

    def poll_for(self, duration_seconds: float) -> None:
        """Poll Hall inputs during the idle time between full sensor updates."""
        end_time = time.monotonic() + max(0.0, float(duration_seconds))
        while time.monotonic() < end_time:
            self.poll_once()
            time.sleep(self.speed_counter.poll_interval_seconds)

    def read(self) -> Tuple[float, int]:
        """Return speed_kmh and cadence_rpm."""
        # Convert rotations per second into wheel speed using circumference.
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

        speed_period = self._format_float(
            self._last_speed_measurement.get("period_seconds")
        )
        speed_avg = self._format_float(
            self._last_speed_measurement.get("average_period_seconds")
        )
        cadence_period = self._format_float(
            self._last_cadence_measurement.get("period_seconds")
        )
        cadence_avg = self._format_float(
            self._last_cadence_measurement.get("average_period_seconds")
        )

        return (
            "HALL DEBUG: "
            "SPEED D3 raw={speed_raw} events={speed_events} "
            "period={speed_period}s avg={speed_avg}s samples={speed_samples} | "
            "CADENCE D4 raw={cadence_raw} events={cadence_events} "
            "period={cadence_period}s avg={cadence_avg}s samples={cadence_samples} | "
            "speed={speed:.2f} km/h cadence={cadence:d} rpm"
        ).format(
            speed_raw=speed_raw,
            speed_events=self._last_speed_measurement.get("event_count", 0),
            speed_period=speed_period,
            speed_avg=speed_avg,
            speed_samples=self._last_speed_measurement.get("sample_count", 0),
            cadence_raw=cadence_raw,
            cadence_events=self._last_cadence_measurement.get("event_count", 0),
            cadence_period=cadence_period,
            cadence_avg=cadence_avg,
            cadence_samples=self._last_cadence_measurement.get("sample_count", 0),
            speed=self._speed_kmh,
            cadence=self._cadence_rpm,
        )

    def stop(self) -> None:
        """Stop both Hall sensor polling threads."""
        self.speed_counter.stop()
        self.cadence_counter.stop()

    def _format_raw(self, raw_value: Any) -> str:
        """Format a raw digital value for debug output."""
        if raw_value is None:
            return "INVALID"
        return str(raw_value)

    def _format_float(self, value: Any) -> str:
        """Format optional float debug values."""
        if value is None:
            return "N/A"
        try:
            return "{:.3f}".format(float(value))
        except Exception:
            return "N/A"

    def _clean_speed_kmh(self, value: float) -> float:
        """Reject impossible speed spikes from noisy Hall readings."""
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
        """Reject impossible cadence spikes from noisy Hall readings."""
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
        """Print each combined-sensor warning once."""
        if message == self._last_error:
            return
        self._last_error = message
        print(message)
