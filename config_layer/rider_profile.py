"""Default rider profile used by the local decision layer."""

from __future__ import annotations

from typing import Any
## this file is used as tmp to get the user values we will than make them dynamic and use as input

DEFAULT_RIDER_PROFILE: dict[str, Any] = {
    "rider_id": "rider_001",
    "age": 20,
    "weight_kg": 75,
    "resting_hr_bpm": 70,
    "fitness_level": "normal",
}


def get_default_rider_profile() -> dict[str, Any]:
    """Return a copy of the default rider profile."""
    return DEFAULT_RIDER_PROFILE.copy()
