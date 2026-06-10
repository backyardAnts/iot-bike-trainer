"""Workout-specific rule checks after physical safety is clear.

These rules decide what short message belongs on the LCD after the bike has
already passed the immediate obstacle checks.
"""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from ai_decision_layer.heart_rate_analyzer import (
    calculate_hr_percent,
    is_heart_rate_available,
)
from config_layer.training_profiles import get_training_profile


HR_WARNING_PERCENT = 0.85
HR_RECOVERY_PERCENT = 0.90
LCD_LINE_MAX_LENGTH = 16

HR_WARNING_ACTIONS = {
    "speed": ("Reduce speed", "reduce_speed"),
    "cadence": ("Slow cadence", "slow_cadence"),
    "endurance": ("Reduce effort", "reduce_effort"),
    "vo2_max": ("Near limit", "near_limit"),
}
# Urgent actions trigger a short pulse so the rider notices the warning.
URGENT_WORKOUT_ACTIONS = {
    "recover",
    "reduce_speed",
    "slow_cadence",
    "reduce_effort",
    "near_limit",
}
URGENT_WORKOUT_BUZZER_PULSE_MS = 500


def check_workout(
    sensor_message: dict[str, Any],
    workout_type: str,
    rider_profile: dict[str, Any],
) -> DecisionResult:
    """Return workout-specific LCD guidance for the current safe reading."""
    # Validate first, then normalize readings into simple numeric values.
    get_training_profile(workout_type)
    speed_kmh = _to_float(sensor_message.get("speed_kmh"), 0.0)
    cadence_rpm = _to_int(sensor_message.get("cadence_rpm"), 0)
    heart_rate_bpm, hr_percent = _get_heart_rate_values(
        sensor_message,
        rider_profile,
    )
    lcd_line_1 = _format_lcd_status_line(speed_kmh, heart_rate_bpm, hr_percent)

    # Heart-rate safety overrides the normal goal for every workout type.
    hr_override = _check_hr_override(
        workout_type,
        lcd_line_1,
        heart_rate_bpm,
        hr_percent,
    )
    if hr_override is not None:
        return hr_override

    if workout_type == "endurance":
        return _check_endurance_workout(
            workout_type,
            lcd_line_1,
            heart_rate_bpm,
            hr_percent,
        )

    if workout_type == "speed":
        return _check_speed_workout(
            workout_type,
            lcd_line_1,
            speed_kmh,
            heart_rate_bpm,
            hr_percent,
        )

    if workout_type == "cadence":
        return _check_cadence_workout(
            workout_type,
            lcd_line_1,
            cadence_rpm,
            heart_rate_bpm,
            hr_percent,
        )

    if workout_type == "vo2_max":
        return _check_vo2_max_workout(
            workout_type,
            lcd_line_1,
            heart_rate_bpm,
            hr_percent,
        )

    get_training_profile(workout_type)
    return _guidance_decision(
        workout_type=workout_type,
        lcd_line_1=lcd_line_1,
        lcd_line_2="Maintain pace",
        recommended_action="maintain_pace",
        heart_rate_bpm=heart_rate_bpm,
        hr_percent=hr_percent,
    )


def _check_endurance_workout(
    workout_type: str,
    lcd_line_1: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    """Coach steady endurance effort mostly from heart-rate percentage."""
    if hr_percent is None:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Check watch",
            "check_watch",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent < 0.50:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Increase effort",
            "increase_effort",
            heart_rate_bpm,
            hr_percent,
            alert_level="info",
        )
    if hr_percent < 0.70:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Maintain pace",
            "maintain_pace",
            heart_rate_bpm,
            hr_percent,
            alert_level="normal",
        )
    return _guidance_decision(
        workout_type,
        lcd_line_1,
        "Ease slightly",
        "ease_slightly",
        heart_rate_bpm,
        hr_percent,
        alert_level="info",
    )


def _check_speed_workout(
    workout_type: str,
    lcd_line_1: str,
    speed_kmh: float,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    """Coach speed sessions from the current speed reading."""
    if speed_kmh < 10.0:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Increase speed",
            "increase_speed",
            heart_rate_bpm,
            hr_percent,
            alert_level="info",
        )
    if speed_kmh > 18.0:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Strong pace",
            "strong_pace",
            heart_rate_bpm,
            hr_percent,
            alert_level="normal",
        )
    return _guidance_decision(
        workout_type,
        lcd_line_1,
        "Maintain speed",
        "maintain_speed",
        heart_rate_bpm,
        hr_percent,
        alert_level="normal",
    )


def _check_cadence_workout(
    workout_type: str,
    lcd_line_1: str,
    cadence_rpm: int,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    """Coach cadence sessions from the current cadence reading."""
    if cadence_rpm > 95:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Slow cadence",
            "slow_cadence",
            heart_rate_bpm,
            hr_percent,
            alert_level="info",
        )
    if cadence_rpm < 60:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Pedal faster",
            "pedal_faster",
            heart_rate_bpm,
            hr_percent,
            alert_level="info",
        )
    return _guidance_decision(
        workout_type,
        lcd_line_1,
        "Keep cadence",
        "keep_cadence",
        heart_rate_bpm,
        hr_percent,
        alert_level="normal",
    )


def _check_vo2_max_workout(
    workout_type: str,
    lcd_line_1: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult:
    """Coach interval sessions from how close the rider is to high effort."""
    if hr_percent is None:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Check watch",
            "check_watch",
            heart_rate_bpm,
            hr_percent,
        )
    if hr_percent < 0.75:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Push harder",
            "push_harder",
            heart_rate_bpm,
            hr_percent,
            alert_level="info",
        )
    return _guidance_decision(
        workout_type,
        lcd_line_1,
        "Hold interval",
        "hold_interval",
        heart_rate_bpm,
        hr_percent,
        alert_level="normal",
    )


def _guidance_decision(
    workout_type: str,
    lcd_line_1: str,
    lcd_line_2: str,
    recommended_action: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
    alert_level: str = "info",
) -> DecisionResult:
    """Create the common DecisionResult shape for workout guidance."""
    pulse_ms = 0
    pulse_reason = ""
    if recommended_action in URGENT_WORKOUT_ACTIONS:
        # Do not leave the buzzer on; pulse it once for urgent guidance.
        pulse_ms = URGENT_WORKOUT_BUZZER_PULSE_MS
        pulse_reason = "hr_warning"

    return DecisionResult(
        alert_level=alert_level,
        alert_side="none",
        display_active=True,
        display_message=lcd_line_2,
        speaker_message="",
        decision_type="workout_guidance",
        recommended_action=recommended_action,
        workout_type=workout_type,
        lcd_line_1=lcd_line_1,
        lcd_line_2=lcd_line_2,
        buzzer_state=False,
        led_state=False,
        buzzer_pulse_ms=pulse_ms,
        buzzer_pulse_reason=pulse_reason,
        heart_rate_bpm=heart_rate_bpm,
        hr_percent=_rounded_hr_percent(hr_percent),
    )


def _check_hr_override(
    workout_type: str,
    lcd_line_1: str,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> DecisionResult | None:
    """Return a heart-rate warning before normal workout advice is considered."""
    if hr_percent is None:
        return None

    if hr_percent >= HR_RECOVERY_PERCENT:
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            "Recover now",
            "recover",
            heart_rate_bpm,
            hr_percent,
            alert_level="warning",
        )

    if hr_percent >= HR_WARNING_PERCENT:
        lcd_line_2, recommended_action = HR_WARNING_ACTIONS[workout_type]
        return _guidance_decision(
            workout_type,
            lcd_line_1,
            lcd_line_2,
            recommended_action,
            heart_rate_bpm,
            hr_percent,
            alert_level="warning",
        )

    return None


def _get_heart_rate_values(
    sensor_message: dict[str, Any],
    rider_profile: dict[str, Any],
) -> tuple[int, float | None]:
    """Return both raw BPM and percent-of-max HR, if the reading is usable."""
    value = sensor_message.get("heart_rate_bpm")
    if not is_heart_rate_available(value):
        return 0, None

    heart_rate_bpm = _to_int(value, 0)
    return heart_rate_bpm, calculate_hr_percent(heart_rate_bpm, rider_profile)


def _rounded_hr_percent(hr_percent: float | None) -> float | None:
    """Keep stored heart-rate percentages compact and consistent."""
    if hr_percent is None:
        return None
    return round(float(hr_percent), 3)


def _format_lcd_status_line(
    speed_kmh: float,
    heart_rate_bpm: int,
    hr_percent: float | None,
) -> str:
    """Build a 16-character status line for the Grove LCD."""
    speed_text = f"{float(speed_kmh):.1f}"
    hr_text = str(heart_rate_bpm) if hr_percent is not None else "--"
    line = f"SPD {speed_text} HR {hr_text}"
    if len(line) <= LCD_LINE_MAX_LENGTH:
        return line

    compact_line = f"SPD{speed_text} HR{hr_text}"
    if len(compact_line) <= LCD_LINE_MAX_LENGTH:
        return compact_line
    return compact_line[:LCD_LINE_MAX_LENGTH]


def _to_float(value: Any, default: float) -> float:
    """Convert a value to float while keeping a safe fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    """Convert a value to int while keeping booleans out."""
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
