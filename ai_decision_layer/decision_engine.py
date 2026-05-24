"""Main rule-based decision engine for local simulator feedback."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from ai_decision_layer.heart_rate_analyzer import check_heart_rate
from ai_decision_layer.safety_analyzer import check_safety
from ai_decision_layer.workout_analyzer import check_workout
from config_layer.rider_profile import get_default_rider_profile
from config_layer.training_profiles import is_valid_workout_type, normalize_workout_type


class DecisionEngine:
    """Apply safety, heart-rate, and workout rules to one sensor message."""

    def __init__(self, rider_profile: dict[str, Any] | None = None) -> None:
        self.rider_profile = rider_profile or get_default_rider_profile()

    def analyze(self, sensor_message: dict[str, Any]) -> DecisionResult:
        """Return the highest-priority decision for one sensor message."""
        workout_type = self._get_workout_type(sensor_message)
        safety_result = check_safety(sensor_message, workout_type)
        heart_rate_result = check_heart_rate(
            sensor_message,
            self.rider_profile,
            workout_type,
        )

        if _is_alert_level(safety_result, "danger"):
            return safety_result
        if _is_alert_level(heart_rate_result, "danger"):
            return heart_rate_result
        if _is_alert_level(safety_result, "warning"):
            return safety_result
        if _is_alert_level(heart_rate_result, "warning"):
            return heart_rate_result

        workout_result = check_workout(
            sensor_message,
            workout_type,
            self.rider_profile,
        )
        if workout_result is not None:
            return workout_result

        return DecisionResult(
            alert_level="normal",
            alert_side="none",
            display_active=False,
            display_message="Maintain pace",
            speaker_message="",
            decision_type="normal",
            recommended_action="maintain",
            workout_type=workout_type,
        )

    def _get_workout_type(self, sensor_message: dict[str, Any]) -> str:
        workout_type = str(sensor_message.get("workout_type", "")).strip()
        if not is_valid_workout_type(workout_type):
            supported = "speed, cadence, endurance, vo2_max"
            raise ValueError(
                f"Invalid workout type in sensor message: {workout_type}. "
                f"Choose one of: {supported}."
            )

        return normalize_workout_type(workout_type)


def _is_alert_level(
    decision_result: DecisionResult | None,
    alert_level: str,
) -> bool:
    return decision_result is not None and decision_result.alert_level == alert_level
