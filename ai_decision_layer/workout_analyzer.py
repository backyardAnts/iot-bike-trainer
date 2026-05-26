"""Workout-specific rule checks after physical safety is clear."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from ai_decision_layer.heart_rate_analyzer import (
    calculate_hr_percent,
    is_heart_rate_available,
)
from config_layer.training_profiles import get_training_profile


HIGH_HR_PERCENT = 0.85

WORKOUT_LCD_TITLES = {
    "endurance": "ENDURANCE",
    "speed": "SPEED",
    "cadence": "CADENCE",
    "vo2_max": "VO2 MAX",
}


def check_workout(
    sensor_message: dict[str, Any],
    workout_type: str,
    rider_profile: dict[str, Any],
) -> DecisionResult:
    """Return workout-specific LCD guidance for the current safe reading."""
    get_training_profile(workout_type)
    speed_kmh = _to_float(sensor_message.get("speed_kmh"), 0.0)
    cadence_rpm = _to_int(sensor_message.get("cadence_rpm"), 0)
    heart_rate_bpm, hr_percent = _get_heart_rate_values(
        sensor_message,
        rider_profile,
    )

    if workout_type == "endurance":
        return _check_endurance_workout(workout_type, heart_rate_bpm, hr_percent)

    if workout_type == "speed":
        return _check_speed_workout(
            workout_type,
            speed_kmh,
            heart_rate_bpm,
            hr_percent,
        )

    if workout_type == "cadence":
        return _check_cadence_workout(
            workout_type,
            cadence_rpm,
            heart_rate_bpm,
            hr_percent,
        )

    if workout_type == "vo2_max":
        return _check_vo2_max_workout(workout_type, heart_rate_bpm, hr_percent)

    get_training_profile(workout_type)
    return _guidance_decision(
        workout_type=workout_type,
        lcd_line_2="Maintain pace",
        recommended_action="maintain_pace",
        heart_rate_bpm=heart_rate_bpm,
        hr_percent=hr_percent,
    )


def _check_endurance_workout(
    workout_type: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    if hr_percent is None:
        return _guidance_decision(
            workout_type,
            "HR unavailable",
            "hr_unavailable",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent < 0.50:
        return _guidance_decision(
            workout_type,
            "Increase effort",
            "increase_effort",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent <= 0.70:
        return _guidance_decision(
            workout_type,
            "Maintain pace",
            "maintain_pace",
            heart_rate_bpm,
            hr_percent,
        )
    return _guidance_decision(
        workout_type,
        "Reduce effort",
        "reduce_effort",
        heart_rate_bpm,
        hr_percent,
    )


def _check_speed_workout(
    workout_type: str,
    speed_kmh: float,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    if hr_percent is not None and hr_percent > HIGH_HR_PERCENT:
        return _guidance_decision(
            workout_type,
            "Recover now",
            "recover_now",
            heart_rate_bpm,
            hr_percent,
        )
    if speed_kmh < 10.0:
        return _guidance_decision(
            workout_type,
            "Increase speed",
            "increase_speed",
            heart_rate_bpm,
            hr_percent,
        )
    return _guidance_decision(
        workout_type,
        "Maintain speed",
        "maintain_speed",
        heart_rate_bpm,
        hr_percent,
    )


def _check_cadence_workout(
    workout_type: str,
    cadence_rpm: int,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    if cadence_rpm > 95 and hr_percent is not None and hr_percent > HIGH_HR_PERCENT:
        return _guidance_decision(
            workout_type,
            "Slow cadence",
            "slow_cadence",
            heart_rate_bpm,
            hr_percent,
        )
    if cadence_rpm < 60:
        return _guidance_decision(
            workout_type,
            "Pedal faster",
            "pedal_faster",
            heart_rate_bpm,
            hr_percent,
        )
    return _guidance_decision(
        workout_type,
        "Keep cadence",
        "keep_cadence",
        heart_rate_bpm,
        hr_percent,
    )


def _check_vo2_max_workout(
    workout_type: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    if hr_percent is None:
        return _guidance_decision(
            workout_type,
            "HR unavailable",
            "hr_unavailable",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent < 0.75:
        return _guidance_decision(
            workout_type,
            "Push harder",
            "push_harder",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent <= 0.90:
        return _guidance_decision(
            workout_type,
            "Hold interval",
            "hold_interval",
            heart_rate_bpm,
            hr_percent,
        )
    return _guidance_decision(
        workout_type,
        "Recover now",
        "recover_now",
        heart_rate_bpm,
        hr_percent,
    )


def _guidance_decision(
    workout_type: str,
    lcd_line_2: str,
    recommended_action: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    lcd_line_1 = WORKOUT_LCD_TITLES[workout_type]
    return DecisionResult(
        alert_level="info",
        alert_side="none",
        display_active=True,
        display_message=f"{lcd_line_1} / {lcd_line_2}",
        speaker_message="",
        decision_type="workout_guidance",
        recommended_action=recommended_action,
        workout_type=workout_type,
        lcd_line_1=lcd_line_1,
        lcd_line_2=lcd_line_2,
        buzzer_state=False,
        led_state=False,
        heart_rate_bpm=heart_rate_bpm,
        hr_percent=_rounded_hr_percent(hr_percent),
    )


def _get_heart_rate_values(
    sensor_message: dict[str, Any],
    rider_profile: dict[str, Any],
) -> tuple[int, float | None]:
    value = sensor_message.get("heart_rate_bpm")
    if not is_heart_rate_available(value):
        return 0, None

    heart_rate_bpm = _to_int(value, 0)
    return heart_rate_bpm, calculate_hr_percent(heart_rate_bpm, rider_profile)


def _rounded_hr_percent(hr_percent: float | None) -> float | None:
    if hr_percent is None:
        return None
    return round(float(hr_percent), 3)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
