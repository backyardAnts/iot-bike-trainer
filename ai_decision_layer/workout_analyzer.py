"""Workout-specific rule checks after safety checks are clear."""

from __future__ import annotations

from typing import Any

from ai_decision_layer.decision_result import DecisionResult
from ai_decision_layer.heart_rate_analyzer import estimate_max_hr
from config_layer.thresholds import HR_ZONES
from config_layer.training_profiles import get_training_profile


def check_workout(
    sensor_message: dict[str, Any],
    workout_type: str,
    rider_profile: dict[str, Any],
) -> DecisionResult:
    """Return simple workout-specific feedback for the current reading."""
    profile = get_training_profile(workout_type)
    speed_kmh = float(sensor_message["speed_kmh"])
    cadence_rpm = int(sensor_message["cadence_rpm"])
    heart_rate_bpm = int(sensor_message["heart_rate_bpm"])

    target_cadence_min = int(profile["target_cadence_min"])
    target_cadence_max = int(profile["target_cadence_max"])

    if workout_type == "cadence":
        return _check_cadence_workout(
            cadence_rpm,
            target_cadence_min,
            target_cadence_max,
            workout_type,
        )

    if workout_type == "speed":
        return _check_speed_workout(
            speed_kmh,
            cadence_rpm,
            target_cadence_min,
            workout_type,
        )

    if workout_type == "endurance":
        return _check_endurance_workout(
            cadence_rpm,
            target_cadence_min,
            target_cadence_max,
            workout_type,
        )

    if workout_type == "vo2_max":
        return _check_vo2_max_workout(
            speed_kmh,
            cadence_rpm,
            heart_rate_bpm,
            target_cadence_min,
            str(profile["target_hr_zone"]),
            rider_profile,
            workout_type,
        )

    get_training_profile(workout_type)
    return _normal_decision("Maintain steady pace", "maintain", workout_type)


def _check_cadence_workout(
    cadence_rpm: int,
    target_cadence_min: int,
    target_cadence_max: int,
    workout_type: str,
) -> DecisionResult:
    if cadence_rpm < target_cadence_min:
        return _info_decision(
            "Increase cadence slightly",
            "increase_cadence",
            workout_type,
        )
    if cadence_rpm > target_cadence_max:
        return _info_decision(
            "Cadence too high. Control your rhythm",
            "decrease_cadence",
            workout_type,
        )

    return _normal_decision(
        "Good cadence rhythm. Maintain it",
        "maintain",
        workout_type,
    )


def _check_speed_workout(
    speed_kmh: float,
    cadence_rpm: int,
    target_cadence_min: int,
    workout_type: str,
) -> DecisionResult:
    if speed_kmh < 15:
        return _info_decision(
            "Increase speed gradually",
            "increase_speed",
            workout_type,
        )
    if cadence_rpm < target_cadence_min:
        return _info_decision(
            "Increase cadence to support speed",
            "increase_cadence",
            workout_type,
        )

    return _normal_decision(
        "Good speed effort. Maintain this pace",
        "maintain",
        workout_type,
    )


def _check_endurance_workout(
    cadence_rpm: int,
    target_cadence_min: int,
    target_cadence_max: int,
    workout_type: str,
) -> DecisionResult:
    if cadence_rpm < target_cadence_min:
        return _info_decision(
            "Increase cadence slightly for steady endurance",
            "increase_cadence",
            workout_type,
        )
    if cadence_rpm > target_cadence_max:
        return _info_decision(
            "Lower cadence slightly and keep a steady rhythm",
            "decrease_cadence",
            workout_type,
        )

    return _normal_decision(
        "Maintain steady endurance pace",
        "maintain",
        workout_type,
    )


def _check_vo2_max_workout(
    speed_kmh: float,
    cadence_rpm: int,
    heart_rate_bpm: int,
    target_cadence_min: int,
    target_hr_zone: str,
    rider_profile: dict[str, Any],
    workout_type: str,
) -> DecisionResult:
    if speed_kmh < 18 and _is_below_hr_zone(
        heart_rate_bpm,
        target_hr_zone,
        rider_profile,
    ):
        return _info_decision(
            "Push harder for this interval",
            "increase_speed",
            workout_type,
        )
    if cadence_rpm < target_cadence_min:
        return _info_decision(
            "Increase cadence for the interval",
            "increase_cadence",
            workout_type,
        )

    return _normal_decision(
        "Good interval effort. Maintain intensity",
        "maintain",
        workout_type,
    )


def _is_below_hr_zone(
    heart_rate_bpm: int,
    target_hr_zone: str,
    rider_profile: dict[str, Any],
) -> bool:
    zone = HR_ZONES[target_hr_zone]
    max_hr = estimate_max_hr(rider_profile.get("age", 20))
    return heart_rate_bpm < (max_hr * float(zone["min_percent"]))


def _info_decision(
    display_message: str,
    recommended_action: str,
    workout_type: str,
) -> DecisionResult:
    return DecisionResult(
        alert_level="info",
        alert_side="none",
        display_active=True,
        display_message=display_message,
        speaker_message=display_message,
        decision_type="workout",
        recommended_action=recommended_action,
        workout_type=workout_type,
    )


def _normal_decision(
    display_message: str,
    recommended_action: str,
    workout_type: str,
) -> DecisionResult:
    return DecisionResult(
        alert_level="normal",
        alert_side="none",
        display_active=False,
        display_message=display_message,
        speaker_message="",
        decision_type="normal",
        recommended_action=recommended_action,
        workout_type=workout_type,
    )
