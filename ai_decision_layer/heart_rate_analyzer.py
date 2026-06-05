"""Personalized heart-rate safety checks."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from config_layer.thresholds import (
    HR_DANGER_PERCENT_OF_MAX,
    HR_WARNING_PERCENT_OF_MAX,
)

MIN_AVAILABLE_HEART_RATE_BPM = 40
MAX_AVAILABLE_HEART_RATE_BPM = 220


def estimate_max_hr(age: int | float) -> float:
    """Estimate max heart rate using the demo 220-age formula."""
    return max(1.0, 220.0 - float(age))


def is_heart_rate_available(value: Any) -> bool:
    """Return True when the heart-rate value can be used for guidance."""
    if value is None or isinstance(value, bool):
        return False

    try:
        heart_rate_bpm = int(value)
    except (TypeError, ValueError):
        return False

    return (
        MIN_AVAILABLE_HEART_RATE_BPM
        <= heart_rate_bpm
        <= MAX_AVAILABLE_HEART_RATE_BPM
    )


def calculate_hr_percent(
    heart_rate_bpm: int | float,
    rider_profile: dict[str, Any],
) -> float:
    """Return heart rate as a fraction of estimated maximum heart rate."""
    max_hr = _get_max_heart_rate(rider_profile)
    return float(heart_rate_bpm) / max_hr


def calculate_hr_thresholds(rider_profile: dict[str, Any]) -> dict[str, float]:
    """Return max, warning, and danger heart-rate thresholds for a rider."""
    max_hr = _get_max_heart_rate(rider_profile)
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
    if not is_heart_rate_available(sensor_message.get("heart_rate_bpm")):
        return None

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


def _get_max_heart_rate(rider_profile: dict[str, Any]) -> float:
    value = rider_profile.get("max_heart_rate")
    if value is not None and not isinstance(value, bool):
        try:
            max_heart_rate = float(value)
        except (TypeError, ValueError):
            max_heart_rate = 0.0
        if max_heart_rate > 0:
            return max_heart_rate
    return estimate_max_hr(rider_profile.get("age", 20))
