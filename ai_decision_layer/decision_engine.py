"""Main rule-based decision engine for local simulator feedback.

The engine checks immediate physical safety first, then falls back to workout
coaching only when the bike area looks safe.
"""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from ai_decision_layer.physical_feedback_decider import decide_physical_feedback
from ai_decision_layer.workout_analyzer import check_workout
from config_layer.rider_profile import get_default_rider_profile
from config_layer.training_profiles import is_valid_workout_type, normalize_workout_type


PHYSICAL_SAFETY_ACTIONS = {"object_left", "object_right", "object_both"}


class DecisionEngine:
    """Apply physical safety and workout rules to one sensor message."""

    def __init__(self, rider_profile: dict[str, Any] | None = None) -> None:
        """Store the rider profile used for heart-rate thresholds."""
        self.rider_profile = rider_profile or get_default_rider_profile()

    def analyze(self, sensor_message: dict[str, Any]) -> DecisionResult:
        """Return the highest-priority decision for one sensor message."""
        workout_type = self._get_workout_type(sensor_message)

        # Physical safety wins over training guidance because nearby objects
        # should interrupt any normal workout advice.
        physical_feedback = decide_physical_feedback(
            {
                **sensor_message,
                "workout_type": workout_type,
            }
        )
        if _is_physical_safety_override(physical_feedback):
            return _physical_feedback_to_result(physical_feedback)

        # At this point the surroundings are safe, so return workout coaching.
        return check_workout(
            sensor_message,
            workout_type,
            self.rider_profile,
        )

    def _get_workout_type(self, sensor_message: dict[str, Any]) -> str:
        """Validate and normalize the workout type stored in a message."""
        workout_type = str(sensor_message.get("workout_type", "")).strip()
        if not is_valid_workout_type(workout_type):
            supported = "speed, cadence, endurance, vo2_max"
            raise ValueError(
                f"Invalid workout type in sensor message: {workout_type}. "
                f"Choose one of: {supported}."
            )

        return normalize_workout_type(workout_type)


def _is_physical_safety_override(feedback: dict[str, Any]) -> bool:
    """Return True when physical feedback should override workout guidance."""
    alert_level = str(feedback.get("alert_level", "")).strip().lower()
    recommended_action = str(feedback.get("recommended_action", "")).strip().lower()
    return alert_level in {"warning", "danger"} or (
        recommended_action in PHYSICAL_SAFETY_ACTIONS
    )


def _physical_feedback_to_result(feedback: dict[str, Any]) -> DecisionResult:
    """Convert the older physical-feedback dictionary into DecisionResult."""
    return DecisionResult(
        alert_level=str(feedback["alert_level"]),
        alert_side=str(feedback["alert_side"]),
        display_active=bool(feedback["display_active"]),
        display_message=str(feedback["display_message"]),
        speaker_message=str(feedback["speaker_message"]),
        decision_type=str(feedback["decision_type"]),
        recommended_action=str(feedback["recommended_action"]),
        workout_type=str(feedback["workout_type"]),
        lcd_line_1=str(feedback.get("lcd_line_1", "")),
        lcd_line_2=str(feedback.get("lcd_line_2", "")),
        buzzer_state=bool(feedback.get("buzzer_state", False)),
        led_state=bool(feedback.get("led_state", False)),
        buzzer_pulse_ms=int(feedback.get("buzzer_pulse_ms", 0)),
        buzzer_pulse_reason=str(feedback.get("buzzer_pulse_reason", "")),
        heart_rate_bpm=int(feedback.get("heart_rate_bpm", 0)),
        hr_percent=feedback.get("hr_percent"),
    )
