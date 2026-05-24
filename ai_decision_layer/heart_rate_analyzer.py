"""Personalized heart-rate safety checks."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from config_layer.thresholds import (
    HR_DANGER_PERCENT_OF_MAX,
    HR_WARNING_PERCENT_OF_MAX,
)


def estimate_max_hr(age: int | float) -> float:
    """Estimate max heart rate using the Tanaka-style formula."""
    return 208 - (0.7 * float(age))


def calculate_hr_thresholds(rider_profile: dict[str, Any]) -> dict[str, float]:
    """Return max, warning, and danger heart-rate thresholds for a rider."""
    max_hr = estimate_max_hr(rider_profile.get("age", 20))
    return {
        "max_hr": max_hr,
        "warning_hr": max_hr * HR_WARNING_PERCENT_OF_MAX,
        "danger_hr": max_hr * HR_DANGER_PERCENT_OF_MAX,
    }


def check_heart_rate(
    sensor_message: dict[str, Any],
    rider_profile: dict[str, Any],
    workout_type: str,
) -> DecisionResult | None:
    """Return a heart-rate decision when the rider is above safety thresholds."""
    heart_rate_bpm = float(sensor_message["heart_rate_bpm"])
    thresholds = calculate_hr_thresholds(rider_profile)

    if heart_rate_bpm >= thresholds["danger_hr"]:
        return DecisionResult(
            alert_level="danger",
            alert_side="none",
            display_active=True,
            display_message="Heart rate too high. Recover now.",
            speaker_message="Heart rate too high. Recover now.",
            decision_type="heart_rate",
            recommended_action="recover",
            workout_type=workout_type,
        )

    if heart_rate_bpm >= thresholds["warning_hr"]:
        return DecisionResult(
            alert_level="warning",
            alert_side="none",
            display_active=True,
            display_message="Heart rate high. Slow down slightly.",
            speaker_message="Heart rate high. Slow down slightly.",
            decision_type="heart_rate",
            recommended_action="slow_down",
            workout_type=workout_type,
        )

    return None
