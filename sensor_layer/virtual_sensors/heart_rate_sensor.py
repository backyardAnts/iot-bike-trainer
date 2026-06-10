"""Stateful virtual heart-rate sensor.

Heart rate reacts slowly to speed and cadence so the readings look like a body
responding to effort, not a sensor jumping instantly.
"""

from __future__ import annotations

import random

from config_layer.settings import (
    DEFAULT_MAX_HEART_RATE_BPM,
    DEFAULT_RESTING_HEART_RATE_BPM,
    HEART_RATE_FALL_RATE,
    HEART_RATE_INITIAL_NOISE_RANGE_BPM,
    HEART_RATE_INTENSITY_WEIGHTS,
    HEART_RATE_MODE_RANGES_BPM,
    HEART_RATE_NOISE_RANGE_BPM,
    HEART_RATE_RISE_FAST,
    HEART_RATE_RISE_NORMAL,
    HEART_RATE_STOPPED_CADENCE_THRESHOLD_RPM,
    HEART_RATE_STOPPED_INTENSITY,
    HEART_RATE_STOPPED_SPEED_THRESHOLD_KMH,
    HEART_RATE_TARGET_NOISE_RANGE_BPM,
    MAX_CADENCE_RPM,
    MAX_HEART_RATE_BPM,
    MAX_SPEED_KMH,
    MIN_HEART_RATE_BPM,
)


class VirtualHeartRateSensor:
    """Simulate heart rate that reacts slowly to cycling intensity."""

    def __init__(
        self,
        resting_hr: int = DEFAULT_RESTING_HEART_RATE_BPM,
        max_hr: int = DEFAULT_MAX_HEART_RATE_BPM,
        rng: random.Random | None = None,
    ) -> None:
        """Create the heart-rate state near resting effort."""
        self.resting_hr = int(resting_hr)
        self.max_hr = min(int(max_hr), MAX_HEART_RATE_BPM)
        self.min_hr = MIN_HEART_RATE_BPM
        self._rng = rng or random.Random()

        initial_noise_low, initial_noise_high = HEART_RATE_INITIAL_NOISE_RANGE_BPM
        self.current_heart_rate_bpm = float(
            _clamp(
                self.resting_hr + self._rng.uniform(initial_noise_low, initial_noise_high),
                self.min_hr,
                self.max_hr,
            )
        )

    def update(self, speed_kmh: float, cadence_rpm: int, riding_mode: str) -> int:
        """Update heart rate from speed, cadence, and riding mode."""
        mode = riding_mode if riding_mode in HEART_RATE_MODE_RANGES_BPM else "easy"
        low, high = HEART_RATE_MODE_RANGES_BPM[mode]

        # Convert speed and cadence into one simple effort score.
        speed_intensity = _clamp(speed_kmh / MAX_SPEED_KMH, 0.0, 1.0)
        cadence_intensity = _clamp(cadence_rpm / MAX_CADENCE_RPM, 0.0, 1.0)
        intensity = (
            speed_intensity * HEART_RATE_INTENSITY_WEIGHTS["speed"]
            + cadence_intensity * HEART_RATE_INTENSITY_WEIGHTS["cadence"]
        )

        if (
            speed_kmh <= HEART_RATE_STOPPED_SPEED_THRESHOLD_KMH
            and cadence_rpm <= HEART_RATE_STOPPED_CADENCE_THRESHOLD_RPM
        ):
            # When both speed and cadence are stopped, drift back toward rest.
            low, high = HEART_RATE_MODE_RANGES_BPM["stopped"]
            intensity = HEART_RATE_STOPPED_INTENSITY

        target_hr = low + ((high - low) * intensity)
        target_noise_low, target_noise_high = HEART_RATE_TARGET_NOISE_RANGE_BPM
        target_hr += self._rng.uniform(target_noise_low, target_noise_high)
        target_hr = _clamp(target_hr, self.min_hr, self.max_hr)

        difference = target_hr - self.current_heart_rate_bpm
        if difference >= 0:
            # Heart rate rises faster during sprint mode than normal riding.
            max_step = HEART_RATE_RISE_NORMAL if mode != "sprint" else HEART_RATE_RISE_FAST
        else:
            max_step = HEART_RATE_FALL_RATE

        movement = _clamp(difference, -max_step, max_step)
        noise_low, noise_high = HEART_RATE_NOISE_RANGE_BPM
        self.current_heart_rate_bpm = _clamp(
            self.current_heart_rate_bpm + movement + self._rng.uniform(noise_low, noise_high),
            self.min_hr,
            self.max_hr,
        )

        return int(round(self.current_heart_rate_bpm))

    def get_value(self) -> int:
        """Return the latest simulated heart rate."""
        return int(round(self.current_heart_rate_bpm))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Keep a value inside the configured range."""
    return max(minimum, min(maximum, value))
