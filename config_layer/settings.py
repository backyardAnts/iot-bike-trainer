"""General settings and simulation limits for the bike trainer project."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


DEVICE_ID = "bike_001"
DEFAULT_SESSION_ID = "session_001"
DEFAULT_SAMPLE_INTERVAL_SECONDS = 1
DEFAULT_RANDOM_SEED = None
DEFAULT_DISPLAY_ACTIVE = False
DEFAULT_DISPLAY_MESSAGE = ""
DEFAULT_SPEAKER_MESSAGE = ""
DEFAULT_ALERT_LEVEL = "normal"
DEFAULT_ALERT_SIDE = "none"

ALLOWED_ALERT_LEVELS = ("normal", "info", "warning", "danger")
ALLOWED_ALERT_SIDES = ("none", "left", "right", "both")

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "broker.hivemq.com")
MQTT_BROKER_PORT = _env_int("MQTT_BROKER_PORT", 1883)
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_USE_TLS = _env_bool("MQTT_USE_TLS", False)
MQTT_KEEPALIVE_SECONDS = _env_int("MQTT_KEEPALIVE_SECONDS", 60)
MQTT_CLIENT_ID_PREFIX = "anthony_bike_001"

MIN_SPEED_KMH = 0
MAX_SPEED_KMH = 35

MIN_CADENCE_RPM = 0
MAX_CADENCE_RPM = 120

MIN_HEART_RATE_BPM = 70
MAX_HEART_RATE_BPM = 190
DEFAULT_RESTING_HEART_RATE_BPM = 75
DEFAULT_MAX_HEART_RATE_BPM = 190

HEART_RATE_MODE_RANGES_BPM = {
    "stopped": (75, 95),
    "easy": (100, 125),
    "cruising": (125, 155),
    "climbing": (135, 165),
    "sprint": (160, 185),
    "recovery": (95, 125),
}

HEART_RATE_INTENSITY_WEIGHTS = {
    "speed": 0.55,
    "cadence": 0.45,
}

HEART_RATE_STOPPED_SPEED_THRESHOLD_KMH = 0.5
HEART_RATE_STOPPED_CADENCE_THRESHOLD_RPM = 5
HEART_RATE_STOPPED_INTENSITY = 0.15
HEART_RATE_RISE_FAST = 2.8
HEART_RATE_RISE_NORMAL = 1.8
HEART_RATE_FALL_RATE = 1.4
HEART_RATE_INITIAL_NOISE_RANGE_BPM = (-3.0, 4.0)
HEART_RATE_TARGET_NOISE_RANGE_BPM = (-2.0, 2.0)
HEART_RATE_NOISE_RANGE_BPM = (-0.35, 0.35)

MIN_TEMPERATURE_C = 18
MAX_TEMPERATURE_C = 40

MIN_DISTANCE_M = 0.2
MAX_DISTANCE_M = 4.0
