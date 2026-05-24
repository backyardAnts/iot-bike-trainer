"""Global safety checks for all workout types."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from config_layer.thresholds import (
    SIDE_DISTANCE_DANGER_M,
    SIDE_DISTANCE_WARNING_M,
    TEMPERATURE_DANGER_C,
    TEMPERATURE_WARNING_C,
)


def check_safety(sensor_message: dict[str, Any], workout_type: str) -> DecisionResult | None:
    """Return a safety decision when distance or temperature is unsafe."""
    left_distance_m = float(sensor_message["left_distance_m"])
    right_distance_m = float(sensor_message["right_distance_m"])
    temperature_c = float(sensor_message["temperature_c"])

    danger_side = _get_alert_side(
        left_distance_m < SIDE_DISTANCE_DANGER_M,
        right_distance_m < SIDE_DISTANCE_DANGER_M,
    )
    if danger_side != "none":
        return _distance_decision("danger", danger_side, workout_type)

    if temperature_c > TEMPERATURE_DANGER_C:
        return DecisionResult(
            alert_level="danger",
            alert_side="none",
            display_active=True,
            display_message="Danger: temperature too high",
            speaker_message="Danger. Temperature is too high.",
            decision_type="safety",
            recommended_action="high_temperature",
            workout_type=workout_type,
        )

    warning_side = _get_alert_side(
        left_distance_m < SIDE_DISTANCE_WARNING_M,
        right_distance_m < SIDE_DISTANCE_WARNING_M,
    )
    if warning_side != "none":
        return _distance_decision("warning", warning_side, workout_type)

    if temperature_c > TEMPERATURE_WARNING_C:
        return DecisionResult(
            alert_level="warning",
            alert_side="none",
            display_active=True,
            display_message="Warning: temperature is high",
            speaker_message="Temperature is high. Ease up if needed.",
            decision_type="safety",
            recommended_action="high_temperature",
            workout_type=workout_type,
        )

    return None


def _get_alert_side(left_alert: bool, right_alert: bool) -> str:
    if left_alert and right_alert:
        return "both"
    if left_alert:
        return "left"
    if right_alert:
        return "right"
    return "none"


def _distance_decision(
    alert_level: str,
    alert_side: str,
    workout_type: str,
) -> DecisionResult:
    severity = "Danger" if alert_level == "danger" else "Warning"
    display_side_text = _display_side_text(alert_side)
    speaker_side_text = _speaker_side_text(alert_side)
    return DecisionResult(
        alert_level=alert_level,
        alert_side=alert_side,
        display_active=True,
        display_message=f"{severity}: object close on {display_side_text}",
        speaker_message=f"{severity}. Object on {speaker_side_text}.",
        decision_type="safety",
        recommended_action=f"object_{alert_side}",
        workout_type=workout_type,
    )


def _display_side_text(alert_side: str) -> str:
    if alert_side == "both":
        return "both"
    return alert_side


def _speaker_side_text(alert_side: str) -> str:
    if alert_side == "both":
        return "both sides"
    return f"{alert_side} side"
