"""Training profile definitions for workout-type selection."""

from __future__ import annotations

from typing import Any


DEFAULT_WORKOUT_TYPE = "endurance"

TRAINING_PROFILES: dict[str, dict[str, Any]] = {
    "speed": {
        "display_name": "Speed Training",
        "target_cadence_min": 80,
        "target_cadence_max": 100,
        "target_hr_zone": "high",
        "target_speed_behavior": "increase_or_maintain",
        "session_type": "steady_with_sprints",
        "main_metric": "average_speed",
        "feedback_priority": ["speed", "heart_rate", "cadence"],
    },
    "cadence": {
        "display_name": "Cadence Training",
        "target_cadence_min": 75,
        "target_cadence_max": 95,
        "target_hr_zone": "moderate",
        "target_speed_behavior": "stable",
        "session_type": "rhythm_control",
        "main_metric": "cadence_stability",
        "feedback_priority": ["cadence", "heart_rate", "speed"],
    },
    "endurance": {
        "display_name": "Endurance Training",
        "target_cadence_min": 70,
        "target_cadence_max": 90,
        "target_hr_zone": "endurance",
        "target_speed_behavior": "steady",
        "session_type": "long_steady",
        "main_metric": "time_in_zone",
        "feedback_priority": ["heart_rate", "speed_stability", "cadence"],
    },
    "vo2_max": {
        "display_name": "VO2 Max Training",
        "target_cadence_min": 85,
        "target_cadence_max": 105,
        "target_hr_zone": "very_high",
        "target_speed_behavior": "interval_push_recover",
        "session_type": "intervals",
        "main_metric": "interval_effort",
        "feedback_priority": ["heart_rate", "speed", "recovery"],
    },
}

WORKOUT_TYPES = tuple(TRAINING_PROFILES.keys())


def normalize_workout_type(workout_type: str) -> str:
    """Normalize user-provided workout type text."""
    return workout_type.strip().lower().replace("-", "_")


def is_valid_workout_type(workout_type: str) -> bool:
    """Return True when workout_type is one of the supported workout types."""
    return normalize_workout_type(workout_type) in TRAINING_PROFILES


def get_training_profile(workout_type: str) -> dict[str, Any]:
    """Return the training profile for a supported workout type."""
    normalized_workout_type = normalize_workout_type(workout_type)
    if normalized_workout_type not in TRAINING_PROFILES:
        supported = ", ".join(WORKOUT_TYPES)
        raise ValueError(
            f"Unsupported workout type: {workout_type}. "
            f"Supported workout types: {supported}."
        )

    return TRAINING_PROFILES[normalized_workout_type]
