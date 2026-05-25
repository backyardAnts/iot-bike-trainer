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


SAFE_ALERT_DISTANCE_CM = 999.0
WARNING_THRESHOLD_CM = 20.0


class RealBike(object):
    """Read all physical sensors and return the project sensor JSON dictionary."""

    def __init__(
        self,
        device_id: str = settings.DEVICE_ID,
        session_id: Optional[str] = None,
        workout_type: str = DEFAULT_WORKOUT_TYPE,
        heart_rate_bpm: int = 120,
        session_counter_file: Optional[Path] = None,
        lcd_enabled: bool = True,
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
        self.lcd = LcdController(enabled=lcd_enabled) if lcd_enabled else None
        self._latest_message = None  # type: Optional[Dict[str, Any]]
        self._latest_status = ""  # type: str

    def update(self) -> Dict[str, Any]:
        """Read all physical sensors and return one JSON-ready dictionary."""
        temperature = self.temperature_sensor.read()
        left_distance_m, right_distance_m = self.ultrasonic_sensors.read()
        ultrasonic_status = self.ultrasonic_sensors.get_last_status()
        speed_kmh = self.hall_sensors.read_speed_kmh()
        cadence_rpm = self.hall_sensors.read_cadence_rpm()

        feedback = self._build_side_feedback(
            left_distance_m,
            right_distance_m,
            ultrasonic_status,
        )
        buzzer_state = bool(feedback["buzzer_state"])
        self.buzzer.set_state(buzzer_state)
        self._update_lcd(feedback)
        self._latest_status = self._format_status_line(feedback, ultrasonic_status)

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

    def get_latest_status_line(self) -> str:
        """Return the latest terminal-friendly real hardware status line."""
        return self._latest_status

    def get_current_reading(self) -> Dict[str, Any]:
        """Return the latest reading, updating once if needed."""
        if self._latest_message is None:
            return self.update()
        return self._latest_message

    def cleanup(self) -> None:
        """Stop background hardware work and leave outputs off."""
        self.hall_sensors.stop()
        self.buzzer.cleanup()
        if self.lcd is not None:
            self.lcd.cleanup()

    def _build_side_feedback(
        self,
        left_distance_m: float,
        right_distance_m: float,
        ultrasonic_status: Dict[str, Any],
    ) -> Dict[str, Any]:
        left_cm = self._alert_distance_cm(
            left_distance_m,
            bool(ultrasonic_status.get("left_valid")),
        )
        right_cm = self._alert_distance_cm(
            right_distance_m,
            bool(ultrasonic_status.get("right_valid")),
        )
        left_close = left_cm < WARNING_THRESHOLD_CM
        right_close = right_cm < WARNING_THRESHOLD_CM

        if left_close and right_close:
            return {
                "alert_level": "danger",
                "alert_side": "both",
                "display_active": True,
                "display_message": "WARNING BOTH",
                "speaker_message": "Objects on both sides",
                "buzzer_state": True,
                "lcd_line_1": "WARNING BOTH",
                "lcd_line_2": "Object <20cm",
            }
        if left_close:
            return {
                "alert_level": "warning",
                "alert_side": "left",
                "display_active": True,
                "display_message": "WARNING LEFT",
                "speaker_message": "Object on left",
                "buzzer_state": True,
                "lcd_line_1": "WARNING LEFT",
                "lcd_line_2": "Object <20cm",
            }
        if right_close:
            return {
                "alert_level": "warning",
                "alert_side": "right",
                "display_active": True,
                "display_message": "WARNING RIGHT",
                "speaker_message": "Object on right",
                "buzzer_state": True,
                "lcd_line_1": "WARNING RIGHT",
                "lcd_line_2": "Object <20cm",
            }

        return {
            "alert_level": "normal",
            "alert_side": "none",
            "display_active": False,
            "display_message": "SAFE",
            "speaker_message": "",
            "buzzer_state": False,
            "lcd_line_1": "SAFE",
            "lcd_line_2": "No object close",
        }

    def _update_lcd(self, feedback: Dict[str, Any]) -> None:
        if self.lcd is None:
            return

        self.lcd.display(
            str(feedback["lcd_line_1"]),
            str(feedback["lcd_line_2"]),
        )

    def _format_status_line(
        self,
        feedback: Dict[str, Any],
        ultrasonic_status: Dict[str, Any],
    ) -> str:
        return "LEFT: {left} | RIGHT: {right} | STATUS: {status} | BUZZER: {buzzer}".format(
            left=self._format_distance_cm(
                ultrasonic_status.get("left_raw_cm"),
                bool(ultrasonic_status.get("left_valid")),
            ),
            right=self._format_distance_cm(
                ultrasonic_status.get("right_raw_cm"),
                bool(ultrasonic_status.get("right_valid")),
            ),
            status=str(feedback["display_message"]),
            buzzer="ON" if feedback["buzzer_state"] else "OFF",
        )

    def _format_distance_cm(self, raw_cm: Any, valid: bool) -> str:
        if not valid:
            return "INVALID"
        return "{:d} cm".format(int(round(float(raw_cm))))

    def _alert_distance_cm(self, distance_m: float, valid: bool) -> float:
        if not valid:
            return SAFE_ALERT_DISTANCE_CM
        return float(distance_m) * 100.0

    def _normalize_workout_type(self, workout_type: str) -> str:
        get_training_profile(workout_type)
        return normalize_workout_type(workout_type)
