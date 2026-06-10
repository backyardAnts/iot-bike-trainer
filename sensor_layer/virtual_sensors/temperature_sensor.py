"""Stateful virtual outdoor temperature sensor.

Temperature changes slowly because real ambient temperature does not jump from
one sensor sample to the next.
"""

from __future__ import annotations

import random

from config_layer.settings import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C


class VirtualTemperatureSensor:
    """Simulate slowly changing outdoor temperature in Celsius."""

    def __init__(
        self,
        min_temp: float = MIN_TEMPERATURE_C,
        max_temp: float = MAX_TEMPERATURE_C,
        rng: random.Random | None = None,
    ) -> None:
        """Create the temperature state and bounds."""
        self.min_temp = float(min_temp)
        self.max_temp = float(max_temp)
        self._rng = rng or random.Random()

        self.current_temperature_c = self._rng.uniform(25.0, 30.0)
        self._target_temperature_c = self.current_temperature_c
        self._target_updates_remaining = 0

    def update(self) -> float:
        """Move temperature very slowly toward a weather target."""
        if self._target_updates_remaining <= 0:
            self._choose_new_target()

        self._target_updates_remaining -= 1
        difference = self._target_temperature_c - self.current_temperature_c
        movement = _clamp(difference, -0.055, 0.055)
        noise = self._rng.uniform(-0.012, 0.012)

        self.current_temperature_c = _clamp(
            self.current_temperature_c + movement + noise,
            self.min_temp,
            self.max_temp,
        )
        return self.current_temperature_c

    def get_value(self) -> float:
        """Return the latest simulated temperature."""
        return self.current_temperature_c

    def _choose_new_target(self) -> None:
        """Choose a new slow-moving weather target."""
        if self._rng.random() < 0.18:
            # Occasional hot targets allow the safety layer to see warm rides.
            self._target_temperature_c = self._rng.uniform(35.2, self.max_temp)
            self._target_updates_remaining = self._rng.randint(140, 240)
        else:
            self._target_temperature_c = self._rng.uniform(22.0, 34.0)
            self._target_updates_remaining = self._rng.randint(45, 120)

        self._target_temperature_c = _clamp(
            self._target_temperature_c,
            self.min_temp,
            self.max_temp,
        )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Keep a value inside the configured range."""
    return max(minimum, min(maximum, value))
