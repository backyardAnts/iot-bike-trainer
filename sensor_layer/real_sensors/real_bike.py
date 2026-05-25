"""Composite real Raspberry Pi/GrovePi bike sensor layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from common.message_schema import build_sensor_message
from common.session_manager import get_next_session_id
from config_layer import settings
from config_layer.training_profiles import (
    DEFAULT_WORKOUT_TYPE,
    get_training_profile,
    normalize_workout_type,
)
from sensor_layer.real_sensors.buzzer_controller import BuzzerController
from sensor_layer.real_sensors.hall_sensor_counter import SpeedCadenceHallSensors
from sensor_layer.real_sensors.lcd_controller import LcdController
from sensor_layer.real_sensors.temperature_sensor import TemperatureSensor
from sensor_layer.real_sensors.ultrasonic_sensors import UltrasonicSensors


class RealBike(object):
    """Read all physical sensors and return the project sensor JSON dictionary."""

    def __init__(
        self,
        device_id: str = settings.DEVICE_ID,
        session_id: Optional[str] = None,
        workout_type: str = DEFAULT_WORKOUT_TYPE,
        heart_rate_bpm: int = 120,
        session_counter_file: Optional[Path] = None,
    ) -> None:
        self.device_id = str(device_id)
        self.workout_type = self._normalize_workout_type(workout_type)
        self.session_id = (
            str(session_id)
            if session_id is not None
            else get_next_session_id(session_counter_file)
        )
        self.heart_rate_bpm = int(heart_rate_bpm)

        self.temperature_sensor = TemperatureSensor(port=2, sensor_type=0)
        self.ultrasonic_sensors = UltrasonicSensors(left_port=5, right_port=6)
        self.hall_sensors = SpeedCadenceHallSensors(
            speed_port=3,
            cadence_port=4,
            wheel_circumference_m=2.10,
        )
        self.buzzer = BuzzerController(port=7)
        self.lcd = LcdController()
        self._latest_message = None  # type: Optional[Dict[str, Any]]

    def update(self) -> Dict[str, Any]:
        """Read all physical sensors and return one JSON-ready dictionary."""
        temperature = self.temperature_sensor.read()
        left_distance_m, right_distance_m = self.ultrasonic_sensors.read()
        speed_kmh = self.hall_sensors.read_speed_kmh()
        cadence_rpm = self.hall_sensors.read_cadence_rpm()

        feedback = self._build_side_feedback(left_distance_m, right_distance_m)
        buzzer_state = bool(feedback["buzzer_state"])
        self.buzzer.set_state(buzzer_state)
        self._update_lcd(
            feedback,
            speed_kmh=speed_kmh,
            cadence_rpm=cadence_rpm,
        )

        self._latest_message = build_sensor_message(
            device_id=self.device_id,
            session_id=self.session_id,
            workout_type=self.workout_type,
            speed_kmh=speed_kmh,
            cadence_rpm=cadence_rpm,
            heart_rate_bpm=self.heart_rate_bpm,
            temperature_c=temperature["temperature_c"],
            left_distance_m=left_distance_m,
            right_distance_m=right_distance_m,
            display_active=feedback["display_active"],
            display_message=feedback["display_message"],
            speaker_message=feedback["speaker_message"],
            alert_level=feedback["alert_level"],
            alert_side=feedback["alert_side"],
            buzzer_state=buzzer_state,
            led_state=False,
        )
        return self._latest_message

    def get_current_reading(self) -> Dict[str, Any]:
        """Return the latest reading, updating once if needed."""
        if self._latest_message is None:
            return self.update()
        return self._latest_message

    def cleanup(self) -> None:
        """Stop background hardware work and leave outputs off."""
        self.hall_sensors.stop()
        self.buzzer.cleanup()
        self.lcd.cleanup()

    def _build_side_feedback(
        self,
        left_distance_m: float,
        right_distance_m: float,
    ) -> Dict[str, Any]:
        left_close = left_distance_m < 1.0
        right_close = right_distance_m < 1.0

        if left_close and right_close:
            return {
                "alert_level": "danger",
                "alert_side": "both",
                "display_active": True,
                "display_message": "ALERT BOTH",
                "speaker_message": "Vehicles both sides",
                "buzzer_state": True,
            }
        if left_close:
            return {
                "alert_level": "warning",
                "alert_side": "left",
                "display_active": True,
                "display_message": "ALERT LEFT",
                "speaker_message": "Vehicle on left",
                "buzzer_state": True,
            }
        if right_close:
            return {
                "alert_level": "warning",
                "alert_side": "right",
                "display_active": True,
                "display_message": "ALERT RIGHT",
                "speaker_message": "Vehicle on right",
                "buzzer_state": True,
            }

        return {
            "alert_level": "normal",
            "alert_side": "none",
            "display_active": False,
            "display_message": "",
            "speaker_message": "",
            "buzzer_state": False,
        }

    def _update_lcd(
        self,
        feedback: Dict[str, Any],
        speed_kmh: float,
        cadence_rpm: int,
    ) -> None:
        if feedback["display_active"]:
            self.lcd.display(str(feedback["display_message"]), "Check side")
            return

        self.lcd.display(
            "BIKE READY",
            "Spd:{:.0f} Cad:{:d}".format(speed_kmh, int(cadence_rpm)),
        )

    def _normalize_workout_type(self, workout_type: str) -> str:
        get_training_profile(workout_type)
        return normalize_workout_type(workout_type)
