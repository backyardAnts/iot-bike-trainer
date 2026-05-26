"""Physical bike feedback decisions for GrovePi hardware mode."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.heart_rate_analyzer import (
    calculate_hr_percent,
    is_heart_rate_available,
)
from config_layer.rider_profile import get_default_rider_profile


PHYSICAL_WARNING_THRESHOLD_CM = 50.0
SAFE_ALERT_DISTANCE_CM = 999.0


def decide_physical_feedback(sensor_data: dict[str, Any]) -> dict[str, Any]:
    """Return the original real-controller side warning feedback decision."""
    left_cm = _distance_to_alert_cm(sensor_data.get("left_distance_m"))
    right_cm = _distance_to_alert_cm(sensor_data.get("right_distance_m"))
    left_close = left_cm < PHYSICAL_WARNING_THRESHOLD_CM
    right_close = right_cm < PHYSICAL_WARNING_THRESHOLD_CM
    workout_type = str(sensor_data.get("workout_type", ""))

    if left_close and right_close:
        return _with_heart_rate_fields(
            _feedback(
                alert_level="danger",
                alert_side="both",
                display_active=True,
                display_message="WARNING BOTH",
                speaker_message="Objects on both sides",
                buzzer_state=True,
                lcd_line_1="WARNING BOTH",
                lcd_line_2="Object close",
                recommended_action="object_both",
                workout_type=workout_type,
            ),
            sensor_data,
        )

    if left_close:
        return _with_heart_rate_fields(
            _feedback(
                alert_level="warning",
                alert_side="left",
                display_active=True,
                display_message="WARNING LEFT",
                speaker_message="Object on left",
                buzzer_state=True,
                lcd_line_1="WARNING LEFT",
                lcd_line_2="Object close",
                recommended_action="object_left",
                workout_type=workout_type,
            ),
            sensor_data,
        )

    if right_close:
        return _with_heart_rate_fields(
            _feedback(
                alert_level="warning",
                alert_side="right",
                display_active=True,
                display_message="WARNING RIGHT",
                speaker_message="Object on right",
                buzzer_state=True,
                lcd_line_1="WARNING RIGHT",
                lcd_line_2="Object close",
                recommended_action="object_right",
                workout_type=workout_type,
            ),
            sensor_data,
        )

    return _with_heart_rate_fields(
        _feedback(
            alert_level="normal",
            alert_side="none",
            display_active=False,
            display_message="SAFE",
            speaker_message="",
            buzzer_state=False,
            lcd_line_1="SAFE",
            lcd_line_2="No object close",
            recommended_action="safe",
            workout_type=workout_type,
        ),
        sensor_data,
    )


def is_physical_sensor_message(sensor_data: dict[str, Any]) -> bool:
    """Return True for the existing real-hardware sensor JSON shape."""
    return "buzzer_state" in sensor_data and "led_state" in sensor_data


def _feedback(
    alert_level: str,
    alert_side: str,
    display_active: bool,
    display_message: str,
    speaker_message: str,
    buzzer_state: bool,
    lcd_line_1: str,
    lcd_line_2: str,
    recommended_action: str,
    workout_type: str,
) -> dict[str, Any]:
    return {
        "command": "update_feedback",
        "alert_state": alert_level,
        "alert_level": alert_level,
        "alert_side": alert_side,
        "warning_side": alert_side,
        "display_active": display_active,
        "display_message": display_message,
        "speaker_message": speaker_message,
        "buzzer_state": buzzer_state,
        "led_state": False,
        "lcd_line_1": lcd_line_1,
        "lcd_line_2": lcd_line_2,
        "decision_type": "physical_safety",
        "recommended_action": recommended_action,
        "workout_type": workout_type,
    }


def _distance_to_alert_cm(value: Any) -> float:
    try:
        distance_m = float(value)
    except (TypeError, ValueError):
        return SAFE_ALERT_DISTANCE_CM

    if distance_m < 0:
        return SAFE_ALERT_DISTANCE_CM
    return distance_m * 100.0


def _with_heart_rate_fields(
    feedback: dict[str, Any],
    sensor_data: dict[str, Any],
) -> dict[str, Any]:
    value = sensor_data.get("heart_rate_bpm")
    if not is_heart_rate_available(value):
        feedback["heart_rate_bpm"] = 0
        return feedback

    heart_rate_bpm = int(value)
    feedback["heart_rate_bpm"] = heart_rate_bpm
    feedback["hr_percent"] = round(
        calculate_hr_percent(heart_rate_bpm, get_default_rider_profile()),
        3,
    )
    return feedback
