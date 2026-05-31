"""Build, serialize, and lightly validate virtual bike sensor messages."""

from __future__ import annotations

import json
from typing import Any, Dict

from common.time_utils import get_current_timestamp
from config_layer.settings import ALLOWED_ALERT_LEVELS, ALLOWED_ALERT_SIDES
from config_layer.training_profiles import (
    get_training_profile,
    is_valid_workout_type,
    normalize_workout_type,
)

## used to define the structure of the message

REQUIRED_SENSOR_MESSAGE_KEYS = (
    "device_id",
    "timestamp",
    "session_id",
    "workout_type",
    "speed_kmh",
    "cadence_rpm",
    "heart_rate_bpm",
    "temperature_c",
    "left_distance_m",
    "right_distance_m",
    "display_active",
    "display_message",
    "speaker_message",
    "alert_level",
    "alert_side",
)

REAL_SENSOR_MESSAGE_KEYS = REQUIRED_SENSOR_MESSAGE_KEYS + (
    "buzzer_state",
    "led_state",
)
OPTIONAL_SENSOR_MESSAGE_KEYS = (
    "mode",
)

LEGACY_SENSOR_MESSAGE_KEYS = tuple(
    key for key in REQUIRED_SENSOR_MESSAGE_KEYS if key != "workout_type"
)


def build_sensor_message(
    device_id: str,
    session_id: str,
    workout_type: str,
    speed_kmh: float,
    cadence_rpm: int,
    heart_rate_bpm: int,
    temperature_c: float,
    left_distance_m: float,
    right_distance_m: float,
    display_active: bool,
    display_message: str,
    speaker_message: str,
    alert_level: str,
    alert_side: str,
    buzzer_state: Any = None,
    led_state: Any = None,
) -> Dict[str, Any]:
    """Create the standard JSON-ready bike sensor message."""
    get_training_profile(workout_type)
    normalized_workout_type = normalize_workout_type(workout_type)

    message = {
        "device_id": str(device_id),
        "timestamp": get_current_timestamp(),
        "session_id": str(session_id),
        "workout_type": normalized_workout_type,
        "speed_kmh": round(float(speed_kmh), 1),
        "cadence_rpm": int(cadence_rpm),
        "heart_rate_bpm": int(heart_rate_bpm),
        "temperature_c": round(float(temperature_c), 1),
        "left_distance_m": round(float(left_distance_m), 2),
        "right_distance_m": round(float(right_distance_m), 2),
        "display_active": bool(display_active),
        "display_message": str(display_message),
        "speaker_message": str(speaker_message),
        "alert_level": str(alert_level),
        "alert_side": str(alert_side),
    }
    if buzzer_state is not None:
        message["buzzer_state"] = bool(buzzer_state)
    if led_state is not None:
        message["led_state"] = bool(led_state)
    return message


def message_to_json(message: Dict[str, Any]) -> str:
    """Convert a sensor message dictionary to compact JSON text."""
    return json.dumps(message, separators=(",", ":"))


def validate_sensor_message(message: Dict[str, Any]) -> bool:
    """Return True when a message has the expected keys and basic types."""
    if not isinstance(message, dict):
        return False

    message_keys = set(message.keys())
    has_workout_type = "workout_type" in message
    valid_key_sets = (
        set(REQUIRED_SENSOR_MESSAGE_KEYS),
        set(REAL_SENSOR_MESSAGE_KEYS),
        set(LEGACY_SENSOR_MESSAGE_KEYS),
    )
    optional_keys = set(OPTIONAL_SENSOR_MESSAGE_KEYS)
    if not any(
        message_keys == valid_keys or message_keys == valid_keys | optional_keys
        for valid_keys in valid_key_sets
    ):
        return False

    if not isinstance(message["device_id"], str):
        return False
    if not isinstance(message["timestamp"], str):
        return False
    if not isinstance(message["session_id"], str):
        return False
    if has_workout_type:
        if not isinstance(message["workout_type"], str):
            return False
        if not is_valid_workout_type(message["workout_type"]):
            return False
    if not _is_number(message["speed_kmh"]):
        return False
    if not _is_int(message["cadence_rpm"]):
        return False
    if not _is_int(message["heart_rate_bpm"]):
        return False
    if not _is_number(message["temperature_c"]):
        return False
    if not _is_number(message["left_distance_m"]):
        return False
    if not _is_number(message["right_distance_m"]):
        return False
    if not isinstance(message["display_active"], bool):
        return False
    if not isinstance(message["display_message"], str):
        return False
    if not isinstance(message["speaker_message"], str):
        return False
    if not isinstance(message["alert_level"], str):
        return False
    if not isinstance(message["alert_side"], str):
        return False
    if message["alert_level"] not in ALLOWED_ALERT_LEVELS:
        return False
    if message["alert_side"] not in ALLOWED_ALERT_SIDES:
        return False
    if "buzzer_state" in message and not isinstance(message["buzzer_state"], bool):
        return False
    if "led_state" in message and not isinstance(message["led_state"], bool):
        return False

    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
