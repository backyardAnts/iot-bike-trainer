"""Stateful virtual side-distance sensor.

The simulator mostly reports safe side distances but sometimes creates short
close-pass events to exercise safety warnings.
"""

from __future__ import annotations

import random

from config_layer.settings import MAX_DISTANCE_M, MIN_DISTANCE_M
from config_layer.thresholds import DANGER_DISTANCE_M


class VirtualProximitySensor:
    """Simulate left or right side distance readings in meters."""

    def __init__(
        self,
        side: str,
        min_distance: float = MIN_DISTANCE_M,
        max_distance: float = MAX_DISTANCE_M,
        rng: random.Random | None = None,
    ) -> None:
        """Create one side sensor and validate which side it represents."""
        normalized_side = side.lower().strip()
        if normalized_side not in {"left", "right"}:
            raise ValueError('side must be "left" or "right"')

        self.side = normalized_side
        self.min_distance = float(min_distance)
        self.max_distance = float(max_distance)
        self._rng = rng or random.Random()

        self.current_distance_m = self._rng.uniform(1.8, self.max_distance)
        self._safe_target_distance_m = self.current_distance_m
        self._close_target_distance_m = self.current_distance_m
        self._safe_target_updates_remaining = 0
        self._close_event_updates_remaining = 0

    def update(self) -> float:
        """Update the side distance, including occasional close-pass events."""
        if self._close_event_updates_remaining <= 0:
            # Close events are short; outside those windows the target is safe.
            self._maybe_start_close_event()

        if self._close_event_updates_remaining > 0:
            target = self._close_target_distance_m
            self._close_event_updates_remaining -= 1
            max_step = self._rng.uniform(0.55, 1.05)
        else:
            if self._safe_target_updates_remaining <= 0:
                self._choose_safe_target()
            self._safe_target_updates_remaining -= 1
            target = self._safe_target_distance_m
            max_step = self._rng.uniform(0.08, 0.22)

        difference = target - self.current_distance_m
        movement = _clamp(difference, -max_step, max_step)
        noise = self._rng.uniform(-0.04, 0.04)

        self.current_distance_m = _clamp(
            self.current_distance_m + movement + noise,
            self.min_distance,
            self.max_distance,
        )
        return self.current_distance_m

    def get_value(self) -> float:
        """Return the latest simulated distance."""
        return self.current_distance_m

    def is_dangerous(self, threshold: float = DANGER_DISTANCE_M) -> bool:
        """Return True when the current distance is below the danger threshold."""
        return self.current_distance_m < threshold

    def _maybe_start_close_event(self) -> None:
        """Randomly start a short close-object event."""
        event_probability = 0.035 if self.side == "right" else 0.018
        if self._rng.random() >= event_probability:
            return

        self._close_target_distance_m = self._rng.uniform(0.3, 0.9)
        self._close_event_updates_remaining = self._rng.randint(4, 8)

    def _choose_safe_target(self) -> None:
        """Pick the next safe cruising distance."""
        self._safe_target_distance_m = self._rng.uniform(1.5, self.max_distance)
        self._safe_target_updates_remaining = self._rng.randint(3, 8)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Keep a value inside the configured range."""
    return max(minimum, min(maximum, value))
