"""Build, serialize, and lightly validate virtual bike sensor messages."""

import json
from typing import Any

from common.time_utils import get_current_timestamp


REQUIRED_SENSOR_MESSAGE_KEYS = (
    "device_id",
    "timestamp",
    "session_id",
    "speed_kmh",
    "cadence_rpm",
    "heart_rate_bpm",
    "temperature_c",
    "left_distance_m",
    "right_distance_m",
    "buzzer_state",
)


def build_sensor_message(
    device_id: str,
    session_id: str,
    speed_kmh: float,
    cadence_rpm: int,
    heart_rate_bpm: int,
    temperature_c: float,
    left_distance_m: float,
    right_distance_m: float,
    buzzer_state: bool,
) -> dict[str, Any]:
    """Create the standard JSON-ready bike sensor message."""
    return {
        "device_id": str(device_id),
        "timestamp": get_current_timestamp(),
        "session_id": str(session_id),
        "speed_kmh": round(float(speed_kmh), 1),
        "cadence_rpm": int(cadence_rpm),
        "heart_rate_bpm": int(heart_rate_bpm),
        "temperature_c": round(float(temperature_c), 1),
        "left_distance_m": round(float(left_distance_m), 2),
        "right_distance_m": round(float(right_distance_m), 2),
        "buzzer_state": bool(buzzer_state),
    }


def message_to_json(message: dict[str, Any]) -> str:
    """Convert a sensor message dictionary to compact JSON text."""
    return json.dumps(message, separators=(",", ":"))


def validate_sensor_message(message: dict[str, Any]) -> bool:
    """Return True when a message has the expected keys and basic types."""
    if not isinstance(message, dict):
        return False

    if set(message.keys()) != set(REQUIRED_SENSOR_MESSAGE_KEYS):
        return False

    if not isinstance(message["device_id"], str):
        return False
    if not isinstance(message["timestamp"], str):
        return False
    if not isinstance(message["session_id"], str):
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
    if not isinstance(message["buzzer_state"], bool):
        return False

    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
