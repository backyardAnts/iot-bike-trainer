"""Stateful virtual heart-rate sensor."""

from __future__ import annotations

import random

from config_layer.settings import MAX_HEART_RATE_BPM, MIN_HEART_RATE_BPM


class VirtualHeartRateSensor:
    """Simulate heart rate that reacts slowly to cycling intensity."""

    _MODE_HR_RANGES = {
        "stopped": (75.0, 95.0),
        "easy": (100.0, 125.0),
        "cruising": (125.0, 155.0),
        "climbing": (135.0, 165.0),
        "sprint": (160.0, 185.0),
        "recovery": (95.0, 125.0),
    }

    def __init__(
        self,
        resting_hr: int = 75,
        max_hr: int = MAX_HEART_RATE_BPM,
        rng: random.Random | None = None,
    ) -> None:
        self.resting_hr = int(resting_hr)
        self.max_hr = int(max_hr)
        self.min_hr = MIN_HEART_RATE_BPM
        self._rng = rng or random.Random()

        self.current_heart_rate_bpm = float(
            _clamp(
                self.resting_hr + self._rng.uniform(-3.0, 4.0),
                self.min_hr,
                self.max_hr,
            )
        )

    def update(self, speed_kmh: float, cadence_rpm: int, riding_mode: str) -> int:
        """Update heart rate from speed, cadence, and riding mode."""
        mode = riding_mode if riding_mode in self._MODE_HR_RANGES else "easy"
        low, high = self._MODE_HR_RANGES[mode]

        speed_intensity = _clamp(speed_kmh / 35.0, 0.0, 1.0)
        cadence_intensity = _clamp(cadence_rpm / 120.0, 0.0, 1.0)
        intensity = (speed_intensity * 0.55) + (cadence_intensity * 0.45)

        if speed_kmh <= 0.5 and cadence_rpm <= 5:
            low, high = self._MODE_HR_RANGES["stopped"]
            intensity = 0.15

        target_hr = low + ((high - low) * intensity)
        target_hr += self._rng.uniform(-2.0, 2.0)
        target_hr = _clamp(target_hr, self.min_hr, self.max_hr)

        difference = target_hr - self.current_heart_rate_bpm
        if difference >= 0:
            max_step = 1.8 if mode != "sprint" else 2.8
        else:
            max_step = 1.4

        movement = _clamp(difference, -max_step, max_step)
        self.current_heart_rate_bpm = _clamp(
            self.current_heart_rate_bpm + movement + self._rng.uniform(-0.35, 0.35),
            self.min_hr,
            self.max_hr,
        )

        return int(round(self.current_heart_rate_bpm))

    def get_value(self) -> int:
        """Return the latest simulated heart rate."""
        return int(round(self.current_heart_rate_bpm))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

