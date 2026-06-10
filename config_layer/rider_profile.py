"""Default rider profile used by the local decision layer.

This is the fallback rider data until a real athlete profile is supplied from
the backend or dashboard.
"""

from __future__ import annotations

from typing import Any

from config_layer.settings import USER_AGE

# Keep this small because callers usually copy it and add session-specific data.
DEFAULT_RIDER_PROFILE: dict[str, Any] = {
    "rider_id": "rider_001",
    "age": USER_AGE,
    "weight_kg": 75,
    "resting_hr_bpm": 70,
    "fitness_level": "normal",
}


def get_default_rider_profile() -> dict[str, Any]:
    """Return a copy of the default rider profile."""
    return DEFAULT_RIDER_PROFILE.copy()
