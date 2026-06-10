"""Stateful virtual bike speed sensor.

Speed moves toward mode-specific targets so the simulator feels like a real
rider changing effort instead of random unrelated numbers.
"""

from __future__ import annotations

import random

from config_layer.settings import MAX_SPEED_KMH, MIN_SPEED_KMH


class VirtualSpeedSensor:
    """Simulate smooth, stateful bicycle speed in km/h."""

    _MODE_RANGES = {
        # Each mode has a realistic speed window in km/h.
        "stopped": (0.0, 0.0),
        "easy": (8.0, 16.0),
        "cruising": (18.0, 28.0),
        "climbing": (10.0, 20.0),
        "sprint": (28.0, 35.0),
        "recovery": (5.0, 14.0),
    }

    _MODE_WEIGHTS = {
        # Higher weights make that riding mode appear more often.
        "stopped": 8,
        "easy": 24,
        "cruising": 34,
        "climbing": 14,
        "sprint": 6,
        "recovery": 14,
    }

    def __init__(
        self,
        min_speed: float = MIN_SPEED_KMH,
        max_speed: float = MAX_SPEED_KMH,
        rng: random.Random | None = None,
    ) -> None:
        """Set speed bounds and initial simulator state."""
        self.min_speed = float(min_speed)
        self.max_speed = float(max_speed)
        self._rng = rng or random.Random()

        self.current_speed_kmh = 0.0
        self.target_speed_kmh = 0.0
        self.riding_mode = "stopped"
        self._target_updates_remaining = 1

    def update(self) -> float:
        """Move speed gradually toward the current riding-mode target."""
        if self._target_updates_remaining <= 0:
            # Keep a target for several updates so speed changes smoothly.
            self._choose_new_target()

        self._target_updates_remaining -= 1
        difference = self.target_speed_kmh - self.current_speed_kmh

        if difference >= 0:
            # Accelerating and slowing down use different step sizes.
            max_step = self._rng.uniform(0.45, 1.35)
            if self.riding_mode == "sprint":
                max_step = self._rng.uniform(0.9, 1.9)
        else:
            max_step = self._rng.uniform(0.55, 1.65)

        movement = _clamp(difference, -max_step, max_step)
        noise = 0.0 if self.riding_mode == "stopped" else self._rng.uniform(-0.12, 0.12)

        self.current_speed_kmh = _clamp(
            self.current_speed_kmh + movement + noise,
            self.min_speed,
            self.max_speed,
        )

        if self.riding_mode == "stopped" and self.current_speed_kmh < 0.4:
            # Avoid tiny rolling values when the simulated rider has stopped.
            self.current_speed_kmh = 0.0

        return self.current_speed_kmh

    def get_value(self) -> float:
        """Return the latest simulated speed."""
        return self.current_speed_kmh

    def _choose_new_target(self) -> None:
        """Choose a new riding mode and target speed for the next few readings."""
        modes = list(self._MODE_WEIGHTS)
        weights = [self._MODE_WEIGHTS[mode] for mode in modes]
        self.riding_mode = self._rng.choices(modes, weights=weights, k=1)[0]

        low, high = self._MODE_RANGES[self.riding_mode]
        self.target_speed_kmh = self._rng.uniform(low, high)

        if self.riding_mode == "stopped":
            self._target_updates_remaining = self._rng.randint(3, 6)
        elif self.riding_mode == "sprint":
            self._target_updates_remaining = self._rng.randint(3, 5)
        else:
            self._target_updates_remaining = self._rng.randint(5, 11)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Keep a value inside the configured range."""
    return max(minimum, min(maximum, value))
