"""Stateful virtual cadence sensor."""

from __future__ import annotations

import random

from config_layer.settings import MAX_CADENCE_RPM, MIN_CADENCE_RPM


class VirtualCadenceSensor:
    """Simulate pedaling cadence that follows speed and riding mode."""

    _MODE_TARGET_RANGES = {
        "stopped": (0.0, 0.0),
        "easy": (50.0, 75.0),
        "cruising": (75.0, 95.0),
        "climbing": (60.0, 85.0),
        "sprint": (95.0, 115.0),
        "recovery": (50.0, 75.0),
    }

    def __init__(
        self,
        min_cadence: int = MIN_CADENCE_RPM,
        max_cadence: int = MAX_CADENCE_RPM,
        rng: random.Random | None = None,
    ) -> None:
        self.min_cadence = int(min_cadence)
        self.max_cadence = int(max_cadence)
        self._rng = rng or random.Random()

        self.current_cadence_rpm = 0.0
        self._target_cadence_rpm = 0.0
        self._target_updates_remaining = 0
        self._anomaly_updates_remaining = 0
        self._anomaly_type: str | None = None

    def update(self, speed_kmh: float, riding_mode: str) -> int:
        """Update cadence using current speed and riding mode."""
        if speed_kmh <= 0.5:
            self._target_cadence_rpm = 0.0
            self._target_updates_remaining = 1
            self._anomaly_updates_remaining = 0
            self._anomaly_type = None
        else:
            if self._target_updates_remaining <= 0:
                self._choose_new_target(speed_kmh, riding_mode)
            self._target_updates_remaining -= 1

        target = self._target_cadence_rpm
        difference = target - self.current_cadence_rpm
        max_step = 12.0 if target == 0.0 else self._rng.uniform(3.5, 7.0)
        movement = _clamp(difference, -max_step, max_step)
        noise = 0.0 if target == 0.0 else self._rng.uniform(-1.0, 1.0)

        self.current_cadence_rpm = _clamp(
            self.current_cadence_rpm + movement + noise,
            self.min_cadence,
            self.max_cadence,
        )

        if speed_kmh <= 0.5 and self.current_cadence_rpm < 3:
            self.current_cadence_rpm = 0.0

        return int(round(self.current_cadence_rpm))

    def get_value(self) -> int:
        """Return the latest simulated cadence."""
        return int(round(self.current_cadence_rpm))

    def _choose_new_target(self, speed_kmh: float, riding_mode: str) -> None:
        mode = riding_mode if riding_mode in self._MODE_TARGET_RANGES else "easy"

        if self._anomaly_updates_remaining <= 0 and self._rng.random() < 0.05:
            self._anomaly_type = self._rng.choice(["low", "high"])
            self._anomaly_updates_remaining = self._rng.randint(2, 5)

        if self._anomaly_updates_remaining > 0 and self._anomaly_type == "low":
            self._target_cadence_rpm = self._rng.uniform(42.0, 58.0)
            self._anomaly_updates_remaining -= 1
        elif self._anomaly_updates_remaining > 0 and self._anomaly_type == "high":
            self._target_cadence_rpm = self._rng.uniform(106.0, 116.0)
            self._anomaly_updates_remaining -= 1
        else:
            low, high = self._MODE_TARGET_RANGES[mode]
            speed_adjustment = _clamp((speed_kmh - 18.0) * 0.35, -8.0, 8.0)
            self._target_cadence_rpm = self._rng.uniform(low, high) + speed_adjustment
            self._anomaly_type = None

        if speed_kmh < 4.0:
            self._target_cadence_rpm = min(self._target_cadence_rpm, 45.0)
        elif speed_kmh < 8.0:
            self._target_cadence_rpm = min(self._target_cadence_rpm, 62.0)

        self._target_cadence_rpm = _clamp(
            self._target_cadence_rpm,
            self.min_cadence,
            self.max_cadence,
        )
        self._target_updates_remaining = self._rng.randint(2, 4)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

