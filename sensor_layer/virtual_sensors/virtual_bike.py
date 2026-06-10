"""Composite virtual bike that exposes one JSON-ready sensor reading.

The virtual bike lets the rest of the project run without Raspberry Pi
hardware by producing realistic, stateful sensor messages.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from common.message_schema import build_sensor_message
from common.session_manager import get_next_session_id
from config_layer import settings
from config_layer.training_profiles import (
    DEFAULT_WORKOUT_TYPE,
    get_training_profile,
    normalize_workout_type,
)
from sensor_layer.virtual_sensors.cadence_sensor import VirtualCadenceSensor
from sensor_layer.virtual_sensors.heart_rate_sensor import VirtualHeartRateSensor
from sensor_layer.virtual_sensors.proximity_sensor import VirtualProximitySensor
from sensor_layer.virtual_sensors.speed_sensor import VirtualSpeedSensor
from sensor_layer.virtual_sensors.temperature_sensor import VirtualTemperatureSensor


class VirtualBike:
    """Combine all Phase 3 virtual sensors behind one update API."""

    def __init__(
        self,
        device_id: str = settings.DEVICE_ID,
        session_id: str | None = None,
        workout_type: str | None = None,
        random_seed: int | None = settings.DEFAULT_RANDOM_SEED,
        session_counter_file: str | Path | None = None,
    ) -> None:
        """Create all virtual sensors and assign a session ID."""
        self.device_id = device_id
        self.workout_type = DEFAULT_WORKOUT_TYPE
        self.set_workout_type(workout_type or DEFAULT_WORKOUT_TYPE)
        self.session_id = (
            str(session_id)
            if session_id is not None
            else get_next_session_id(session_counter_file)
        )
        self.display_active = settings.DEFAULT_DISPLAY_ACTIVE
        self.display_message = settings.DEFAULT_DISPLAY_MESSAGE
        self.speaker_message = settings.DEFAULT_SPEAKER_MESSAGE
        self.alert_level = settings.DEFAULT_ALERT_LEVEL
        self.alert_side = settings.DEFAULT_ALERT_SIDE
        self.session_active = False

        # One master seed makes the whole bike repeatable, while child RNGs stop
        # one sensor from consuming random values intended for another sensor.
        master_rng = random.Random(random_seed)
        self.speed_sensor = VirtualSpeedSensor(rng=_make_child_rng(master_rng))
        self.cadence_sensor = VirtualCadenceSensor(rng=_make_child_rng(master_rng))
        self.heart_rate_sensor = VirtualHeartRateSensor(rng=_make_child_rng(master_rng))
        self.temperature_sensor = VirtualTemperatureSensor(rng=_make_child_rng(master_rng))
        self.left_proximity_sensor = VirtualProximitySensor(
            side="left",
            rng=_make_child_rng(master_rng),
        )
        self.right_proximity_sensor = VirtualProximitySensor(
            side="right",
            rng=_make_child_rng(master_rng),
        )

        self._latest_message: dict[str, Any] | None = None

    def set_workout_type(self, workout_type: str) -> None:
        """Set the selected workout type for future sensor messages."""
        get_training_profile(workout_type)
        self.workout_type = normalize_workout_type(workout_type)

    def update(self) -> dict[str, Any]:
        """Update all sensors in dependency order and return the message."""
        # Speed drives mode, mode helps cadence, and both affect heart rate.
        speed_kmh = self.speed_sensor.update()
        riding_mode = self.speed_sensor.riding_mode
        cadence_rpm = self.cadence_sensor.update(speed_kmh, riding_mode)
        heart_rate_bpm = self.heart_rate_sensor.update(
            speed_kmh,
            cadence_rpm,
            riding_mode,
        )
        temperature_c = self.temperature_sensor.update()
        left_distance_m = self.left_proximity_sensor.update()
        right_distance_m = self.right_proximity_sensor.update()

        self._latest_message = build_sensor_message(
            device_id=self.device_id,
            session_id=self.session_id,
            workout_type=self.workout_type,
            speed_kmh=speed_kmh,
            cadence_rpm=cadence_rpm,
            heart_rate_bpm=heart_rate_bpm,
            temperature_c=temperature_c,
            left_distance_m=left_distance_m,
            right_distance_m=right_distance_m,
            display_active=self.display_active,
            display_message=self.display_message,
            speaker_message=self.speaker_message,
            alert_level=self.alert_level,
            alert_side=self.alert_side,
        )
        return self._latest_message

    def get_current_reading(self) -> dict[str, Any]:
        """Return the latest message, updating once if no reading exists yet."""
        if self._latest_message is None:
            return self.update()
        return self._latest_message

    def set_feedback(
        self,
        display_message: str = settings.DEFAULT_DISPLAY_MESSAGE,
        speaker_message: str = settings.DEFAULT_SPEAKER_MESSAGE,
        alert_level: str = settings.DEFAULT_ALERT_LEVEL,
        alert_side: str = settings.DEFAULT_ALERT_SIDE,
        display_active: bool | str | None = None,
    ) -> None:
        """Set virtual rider feedback without applying automatic AI rules."""
        normalized_alert_level = _normalize_alert_level(alert_level)
        display_text = str(display_message)
        speaker_text = str(speaker_message)

        self.display_active = _resolve_display_active(
            display_active,
            display_text,
            speaker_text,
            normalized_alert_level,
        )
        self.display_message = display_text
        self.speaker_message = speaker_text
        self.alert_level = normalized_alert_level
        self.alert_side = _normalize_alert_side(alert_side)

    def clear_feedback(self) -> None:
        """Reset rider feedback to the blank inactive state."""
        self.set_feedback(
            display_message=settings.DEFAULT_DISPLAY_MESSAGE,
            speaker_message=settings.DEFAULT_SPEAKER_MESSAGE,
            alert_level=settings.DEFAULT_ALERT_LEVEL,
            alert_side=settings.DEFAULT_ALERT_SIDE,
            display_active=settings.DEFAULT_DISPLAY_ACTIVE,
        )

    def set_display_message(self, message: str) -> None:
        """Set the virtual LCD/OLED display message."""
        self.display_message = str(message)
        self.display_active = _should_display_be_active(
            self.display_message,
            self.alert_level,
        )

    def set_speaker_message(self, message: str) -> None:
        """Set the virtual speaker message."""
        self.speaker_message = str(message)
        self.display_active = _should_display_be_active(
            self.display_message,
            self.alert_level,
        )

    def start_session(self) -> None:
        """Mark the current virtual ride session as active."""
        self.session_active = True

    def stop_session(self) -> None:
        """Mark the current virtual ride session as inactive."""
        self.session_active = False

    def is_session_active(self) -> bool:
        """Return whether the virtual ride session is active."""
        return self.session_active


def _make_child_rng(master_rng: random.Random) -> random.Random:
    """Create an independent random generator from the master generator."""
    return random.Random(master_rng.randrange(0, 2**32))


def _normalize_alert_level(alert_level: str) -> str:
    """Keep alert levels within the shared schema values."""
    value = str(alert_level).strip().lower()
    if value in settings.ALLOWED_ALERT_LEVELS:
        return value
    return settings.DEFAULT_ALERT_LEVEL


def _normalize_alert_side(alert_side: str) -> str:
    """Keep alert sides within the shared schema values."""
    value = str(alert_side).strip().lower()
    if value in settings.ALLOWED_ALERT_SIDES:
        return value
    return settings.DEFAULT_ALERT_SIDE


def _resolve_display_active(
    display_active: bool | str | None,
    display_message: str,
    speaker_message: str,
    alert_level: str,
) -> bool:
    """Decide whether the virtual display should be marked active."""
    if display_active is not None:
        return _coerce_bool(display_active)

    return bool(
        display_message
        or speaker_message
        or alert_level in {"warning", "danger"}
    )


def _coerce_bool(value: bool | str) -> bool:
    """Convert booleans and common truthy strings to bool."""
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _should_display_be_active(display_message: str, alert_level: str) -> bool:
    """Turn the display on when there is text or a warning state."""
    return bool(display_message or alert_level in {"warning", "danger"})
