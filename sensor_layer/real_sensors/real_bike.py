"""Composite real Raspberry Pi/GrovePi bike sensor layer."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ai_decision_layer.physical_feedback_decider import (
    PHYSICAL_WARNING_THRESHOLD_CM,
    decide_physical_feedback,
)
from common.message_schema import build_sensor_message
from common.session_manager import get_next_session_id
from config_layer import settings
from config_layer.training_profiles import (
    DEFAULT_WORKOUT_TYPE,
    get_training_profile,
    normalize_workout_type,
)
from sensor_layer.real_sensors.buzzer_controller import BuzzerController
from sensor_layer.real_sensors.lcd_controller import LcdController
from sensor_layer.real_sensors.temperature_sensor import TemperatureSensor
from sensor_layer.real_sensors.ultrasonic_sensors import UltrasonicSensors


WARNING_THRESHOLD_CM = PHYSICAL_WARNING_THRESHOLD_CM
WORKOUT_BUZZER_PULSE_COOLDOWN_SECONDS = 10.0


class RealBike(object):
    """Read all physical sensors and return the project sensor JSON dictionary."""

    def __init__(
        self,
        device_id: str = settings.DEVICE_ID,
        session_id: Optional[str] = None,
        workout_type: str = DEFAULT_WORKOUT_TYPE,
        heart_rate_bpm: int = 0,
        session_counter_file: Optional[Path] = None,
        lcd_enabled: bool = True,
        lcd_debug: bool = False,
        wheel_diameter_cm: float = 70.0,
        speed_magnets_per_rotation: int = 1,
        cadence_magnets_per_rotation: int = 1,
        enable_hall: bool = True,
        hall_debug: bool = False,
        enable_temperature: bool = True,
        temperature_sensor_type: int = 0,
        temperature_debug: bool = False,
        command_feedback_enabled: bool = False,
        command_timeout_seconds: float = 3.0,
        defer_session_creation: bool = False,
    ) -> None:
        self.device_id = str(device_id)
        self.workout_type = self._normalize_workout_type(workout_type)
        self._session_counter_file = session_counter_file
        self._fixed_session_id = session_id is not None
        self._defer_session_creation = bool(defer_session_creation)
        if session_id is not None:
            self.session_id = str(session_id)
        elif self._defer_session_creation:
            self.session_id = ""
        else:
            self.session_id = get_next_session_id(session_counter_file)
        self.workout_active = bool(self.session_id and not self._defer_session_creation)
        self.session_active = self.workout_active
        self.mode = "real"
        self.athlete = {}  # type: Dict[str, Any]
        self.heart_rate_bpm = int(heart_rate_bpm)
        self.enable_hall = bool(enable_hall)
        self.hall_debug = bool(hall_debug)
        self.enable_temperature = bool(enable_temperature)
        self.temperature_debug = bool(temperature_debug)
        self.command_feedback_enabled = bool(command_feedback_enabled)
        self.command_timeout_seconds = float(command_timeout_seconds)
        self._last_hall_error = ""  # type: str

        self.ultrasonic_sensors = UltrasonicSensors(left_port=5, right_port=6)
        self.temperature_sensor = None  # type: Optional[TemperatureSensor]
        if self.enable_temperature:
            self.temperature_sensor = TemperatureSensor(
                port=2,
                sensor_type=temperature_sensor_type,
                fallback_temperature_c=25.0,
                min_read_interval_seconds=2.0,
                debug=temperature_debug,
            )
        self.hall_sensors = None  # type: Optional[Any]
        if self.enable_hall:
            self.hall_sensors = self._create_hall_sensors(
                wheel_diameter_cm,
                speed_magnets_per_rotation,
                cadence_magnets_per_rotation,
                hall_debug,
            )
        self.buzzer = BuzzerController(port=7)
        self.lcd = (
            LcdController(enabled=lcd_enabled, debug=lcd_debug)
            if lcd_enabled
            else None
        )
        self._latest_message = None  # type: Optional[Dict[str, Any]]
        self._latest_status = ""  # type: str
        self._latest_humidity_percent = None  # type: Optional[float]
        self._last_temperature_error = ""  # type: str
        self._latest_feedback = self._build_safe_feedback()
        self._latest_workout_feedback = None  # type: Optional[Dict[str, Any]]
        self._last_command_time = None  # type: Optional[float]
        self._last_lcd_lines = None  # type: Optional[Tuple[str, str]]
        self._last_workout_buzzer_pulse_time = None  # type: Optional[float]
        self._last_workout_buzzer_pulse_action = ""  # type: str

    def show_startup_lcd_message(self) -> None:
        """Display a short startup LCD confirmation if LCD is enabled."""
        if self.lcd is None:
            return
        self.lcd.display("BIKE READY", "LCD OK")

    def update(self) -> Dict[str, Any]:
        """Read all physical sensors and return one JSON-ready dictionary."""
        left_distance_m, right_distance_m = self.ultrasonic_sensors.read()
        ultrasonic_status = self.ultrasonic_sensors.get_last_status()
        speed_kmh, cadence_rpm = self._read_hall_values()
        temperature_c, humidity_percent = self._read_temperature_values()

        feedback_input = self._build_feedback_input(left_distance_m, right_distance_m)
        if self._should_use_local_feedback_fallback():
            feedback = decide_physical_feedback(feedback_input)
            self._apply_hardware_feedback(feedback)
        else:
            feedback = self._latest_feedback

        buzzer_state = bool(feedback["buzzer_state"])
        self._latest_status = self._format_status_line(
            feedback,
            ultrasonic_status,
            speed_kmh,
            cadence_rpm,
            temperature_c,
        )

        self._latest_message = build_sensor_message(
            device_id=self.device_id,
            session_id=self.session_id,
            workout_type=self.workout_type,
            speed_kmh=speed_kmh,
            cadence_rpm=cadence_rpm,
            heart_rate_bpm=self.heart_rate_bpm,
            temperature_c=temperature_c,
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
        self._latest_message["speed_kmh"] = round(float(speed_kmh), 2)
        self._latest_message["mode"] = getattr(self, "mode", "real")
        self._latest_humidity_percent = humidity_percent
        return self._latest_message

    def set_command_feedback_enabled(self, enabled: bool) -> None:
        """Enable or disable backend command feedback mode."""
        self.command_feedback_enabled = bool(enabled)

    def set_workout_type(self, workout_type: str) -> None:
        """Change the workout type used in future sensor messages."""
        self.workout_type = self._normalize_workout_type(workout_type)

    def set_mode(self, mode: str) -> None:
        """Store the current dashboard-selected bike mode."""
        mode_text = str(mode).strip()
        if mode_text:
            self.mode = mode_text

    def start_workout(
        self,
        session_id: Optional[str] = None,
        workout_type: Optional[str] = None,
        mode: Optional[str] = None,
        athlete: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create or resume the current real workout session."""
        self.start_session(
            session_id=session_id,
            workout_type=workout_type,
            mode=mode,
            athlete=athlete,
        )

    def start_session(
        self,
        session_id: Optional[str] = None,
        workout_type: Optional[str] = None,
        mode: Optional[str] = None,
        athlete: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark the real bike workout as active, creating a session ID if needed."""
        if workout_type:
            self.set_workout_type(workout_type)
        if mode:
            self.set_mode(mode)
        self.athlete = dict(athlete) if isinstance(athlete, dict) else {}

        requested_session_id = _clean_optional_text(session_id)
        if requested_session_id is not None:
            self.session_id = requested_session_id
            self._fixed_session_id = True
        elif not self.workout_active:
            if not self._fixed_session_id or not self.session_id:
                self.session_id = get_next_session_id(self._session_counter_file)

        self.workout_active = True
        self.session_active = True

    def stop_workout(self) -> None:
        """Mark the current real workout as inactive."""
        self.stop_session()

    def stop_session(self) -> None:
        """Stop publishing readings for the current workout session."""
        self.workout_active = False
        self.session_active = False

    def is_session_active(self) -> bool:
        """Return whether the real workout is currently active."""
        return self.workout_active

    def test_buzzer(self, duration_seconds: float = 0.2) -> None:
        """Pulse the buzzer once for command-driven hardware testing."""
        self.buzzer.beep(float(duration_seconds))

    def apply_physical_feedback_command(self, command_data: Dict[str, Any]) -> None:
        """Apply an AI/backend feedback command to buzzer and LCD hardware."""
        feedback = self._normalize_feedback_command(command_data)
        self._last_command_time = time.monotonic()

        if self._is_suppressed_backend_safe_feedback(feedback):
            self._apply_backend_safe_feedback(feedback)
            return

        if feedback["decision_type"] == "workout_guidance":
            self._latest_workout_feedback = dict(feedback)

        self._apply_hardware_feedback(feedback)
        self._apply_workout_buzzer_pulse(self._latest_feedback)

    def set_feedback(
        self,
        display_message: str = settings.DEFAULT_DISPLAY_MESSAGE,
        speaker_message: str = settings.DEFAULT_SPEAKER_MESSAGE,
        alert_level: str = settings.DEFAULT_ALERT_LEVEL,
        alert_side: str = settings.DEFAULT_ALERT_SIDE,
        display_active: Any = None,
    ) -> None:
        """Apply generic feedback commands through the real hardware outputs."""
        self.apply_physical_feedback_command(
            {
                "display_active": display_active,
                "display_message": display_message,
                "speaker_message": speaker_message,
                "alert_level": alert_level,
                "alert_side": alert_side,
            }
        )

    def clear_feedback(self) -> None:
        """Reset physical feedback to the safe hardware state."""
        self.apply_physical_feedback_command(self._build_safe_feedback())

    def set_display_message(self, message: str) -> None:
        """Write a display-only message through the LCD."""
        feedback = dict(self._latest_feedback)
        feedback["display_message"] = str(message)
        feedback["display_active"] = bool(message)
        feedback["lcd_line_1"] = str(message)
        feedback["lcd_line_2"] = ""
        self.apply_physical_feedback_command(feedback)

    def set_speaker_message(self, message: str) -> None:
        """Store the speaker message in the current feedback state."""
        feedback = dict(self._latest_feedback)
        feedback["speaker_message"] = str(message)
        self.apply_physical_feedback_command(feedback)

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
        if self.hall_sensors is not None:
            try:
                self.hall_sensors.stop()
            except Exception as exc:
                self._warn_hall_once("Hall cleanup failed: {}".format(exc))
        self.buzzer.cleanup()
        if self.lcd is not None:
            self.lcd.cleanup()

    def _create_hall_sensors(
        self,
        wheel_diameter_cm: float,
        speed_magnets_per_rotation: int,
        cadence_magnets_per_rotation: int,
        hall_debug: bool,
    ) -> Optional[Any]:
        try:
            from sensor_layer.real_sensors.hall_sensor_counter import (
                SpeedCadenceHallSensors,
            )

            return SpeedCadenceHallSensors(
                speed_port=3,
                cadence_port=4,
                wheel_diameter_cm=wheel_diameter_cm,
                speed_magnets_per_rotation=speed_magnets_per_rotation,
                cadence_magnets_per_rotation=cadence_magnets_per_rotation,
                debounce_seconds=0.25,
                debug=hall_debug,
                background_polling=False,
            )
        except Exception as exc:
            self._warn_hall_once(
                "Hall sensors disabled after setup error: {}".format(exc)
            )
            return None

    def _read_hall_values(self) -> Tuple[float, int]:
        if self.hall_sensors is None:
            return 0.0, 0

        try:
            speed_kmh, cadence_rpm = self.hall_sensors.read()
        except Exception as exc:
            self._warn_hall_once("Hall read failed; using 0 values: {}".format(exc))
            return 0.0, 0

        if speed_kmh < 0 or speed_kmh > 80.0:
            self._warn_hall_once(
                "Hall speed ignored: {:.2f} km/h is outside 0-80".format(speed_kmh)
            )
            speed_kmh = 0.0
        if cadence_rpm < 0 or cadence_rpm > 180:
            self._warn_hall_once(
                "Hall cadence ignored: {} rpm is outside 0-180".format(cadence_rpm)
            )
            cadence_rpm = 0

        return round(float(speed_kmh), 2), int(cadence_rpm)

    def _read_temperature_values(self) -> Tuple[float, Optional[float]]:
        if self.temperature_sensor is None:
            return 25.0, None

        try:
            reading = self.temperature_sensor.read()
        except Exception as exc:
            self._warn_temperature_once(
                "Temperature read failed; using fallback: {}".format(exc)
            )
            return 25.0, None

        temperature_c = reading.get("temperature_c")
        humidity_percent = reading.get("humidity_percent")
        if temperature_c is None:
            return 25.0, humidity_percent
        return round(float(temperature_c), 1), humidity_percent

    def _warn_temperature_once(self, message: str) -> None:
        if message == self._last_temperature_error:
            return
        self._last_temperature_error = message
        print(message)

    def wait_between_updates(self, duration_seconds: float) -> None:
        """Wait between full sensor reads while polling Hall inputs if enabled."""
        if self.hall_sensors is None:
            time.sleep(duration_seconds)
            return

        try:
            self.hall_sensors.poll_for(duration_seconds)
        except Exception as exc:
            self._warn_hall_once("Hall polling failed: {}".format(exc))

            time.sleep(duration_seconds)

    def _should_use_local_feedback_fallback(self) -> bool:
        return not self.command_feedback_enabled

    def _build_feedback_input(
        self,
        left_distance_m: float,
        right_distance_m: float,
    ) -> Dict[str, Any]:
        return {
            "workout_type": self.workout_type,
            "left_distance_m": left_distance_m,
            "right_distance_m": right_distance_m,
        }

    def _build_safe_feedback(self) -> Dict[str, Any]:
        return decide_physical_feedback(
            {
                "workout_type": self.workout_type,
                "left_distance_m": 9.99,
                "right_distance_m": 9.99,
            }
        )

    def _apply_hardware_feedback(self, feedback: Dict[str, Any]) -> None:
        self._latest_feedback = self._normalize_feedback_command(feedback)
        self.buzzer.set_state(bool(self._latest_feedback["buzzer_state"]))
        self._update_lcd(self._latest_feedback)

    def _apply_workout_buzzer_pulse(self, feedback: Dict[str, Any]) -> None:
        if feedback.get("decision_type") != "workout_guidance":
            return
        if bool(feedback.get("buzzer_state", False)):
            return

        pulse_ms = _coerce_int(feedback.get("buzzer_pulse_ms", 0), 0)
        if pulse_ms <= 0:
            return

        recommended_action = str(feedback.get("recommended_action", ""))
        now = time.monotonic()
        if (
            recommended_action == self._last_workout_buzzer_pulse_action
            and self._last_workout_buzzer_pulse_time is not None
            and (
                now - self._last_workout_buzzer_pulse_time
            ) < WORKOUT_BUZZER_PULSE_COOLDOWN_SECONDS
        ):
            return

        self.buzzer.beep(pulse_ms / 1000.0)
        self._last_workout_buzzer_pulse_time = now
        self._last_workout_buzzer_pulse_action = recommended_action

    def _is_suppressed_backend_safe_feedback(self, feedback: Dict[str, Any]) -> bool:
        if not self.command_feedback_enabled:
            return False

        return (
            feedback["decision_type"] == "physical_safety"
            and feedback["recommended_action"] == "safe"
            and feedback["alert_level"] not in {"warning", "danger"}
        )

    def _apply_backend_safe_feedback(self, feedback: Dict[str, Any]) -> None:
        self.buzzer.set_state(False)
        if self._latest_workout_feedback is None:
            suppressed_feedback = dict(feedback)
            suppressed_feedback["buzzer_state"] = False
            suppressed_feedback["led_state"] = False
            self._latest_feedback = suppressed_feedback
            return

        restored_feedback = dict(self._latest_workout_feedback)
        restored_feedback["buzzer_state"] = False
        restored_feedback["led_state"] = False
        self._apply_hardware_feedback(restored_feedback)

    def _normalize_feedback_command(self, command_data: Dict[str, Any]) -> Dict[str, Any]:
        safe_feedback = self._build_safe_feedback()
        alert_level = str(command_data.get("alert_level", safe_feedback["alert_level"]))
        alert_side = str(
            command_data.get(
                "alert_side",
                command_data.get("warning_side", safe_feedback["alert_side"]),
            )
        )
        display_message = str(
            command_data.get("display_message", safe_feedback["display_message"])
        )
        speaker_message = str(
            command_data.get("speaker_message", safe_feedback["speaker_message"])
        )
        display_active = _coerce_bool(
            command_data.get("display_active", safe_feedback["display_active"])
        )
        default_buzzer_state = alert_level in {"warning", "danger"}
        buzzer_state = _coerce_bool(
            command_data.get("buzzer_state", default_buzzer_state)
        )
        lcd_line_1 = str(command_data.get("lcd_line_1", display_message))
        lcd_line_2 = str(command_data.get("lcd_line_2", ""))
        if alert_level not in {"warning", "danger"} and not buzzer_state:
            if "lcd_line_1" not in command_data:
                lcd_line_1 = str(safe_feedback["lcd_line_1"])
            if "lcd_line_2" not in command_data:
                lcd_line_2 = str(safe_feedback["lcd_line_2"])

        return {
            "command": str(command_data.get("command", "update_feedback")),
            "alert_state": str(command_data.get("alert_state", alert_level)),
            "alert_level": alert_level,
            "alert_side": alert_side,
            "warning_side": str(command_data.get("warning_side", alert_side)),
            "display_active": display_active,
            "display_message": display_message,
            "speaker_message": speaker_message,
            "buzzer_state": buzzer_state,
            "led_state": _coerce_bool(command_data.get("led_state", False)),
            "buzzer_pulse_ms": _coerce_int(
                command_data.get("buzzer_pulse_ms", 0),
                0,
            ),
            "buzzer_pulse_reason": str(command_data.get("buzzer_pulse_reason", "")),
            "lcd_line_1": lcd_line_1,
            "lcd_line_2": lcd_line_2,
            "decision_type": str(
                command_data.get("decision_type", safe_feedback["decision_type"])
            ),
            "recommended_action": str(
                command_data.get(
                    "recommended_action",
                    safe_feedback["recommended_action"],
                )
            ),
            "workout_type": str(command_data.get("workout_type", self.workout_type)),
        }

    def _update_lcd(self, feedback: Dict[str, Any]) -> None:
        if self.lcd is None:
            return

        lcd_lines = (
            str(feedback.get("lcd_line_1", "")),
            str(feedback.get("lcd_line_2", "")),
        )
        if lcd_lines == self._last_lcd_lines:
            return

        self.lcd.display(lcd_lines[0], lcd_lines[1])
        self._last_lcd_lines = lcd_lines

    def _format_status_line(
        self,
        feedback: Dict[str, Any],
        ultrasonic_status: Dict[str, Any],
        speed_kmh: float,
        cadence_rpm: int,
        temperature_c: float,
    ) -> str:
        status_line = (
            "LEFT: {left} | RIGHT: {right} | STATUS: {status} | "
            "BUZZER: {buzzer} | SPEED: {speed:.1f} km/h | "
            "CADENCE: {cadence:d} rpm | TEMP: {temperature:.1f} C"
        ).format(
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
            speed=float(speed_kmh),
            cadence=int(cadence_rpm),
            temperature=float(temperature_c),
        )
        if self.hall_debug and self.hall_sensors is not None:
            status_line = "{} | {}".format(
                status_line,
                self.hall_sensors.get_debug_text(),
            )
        return status_line

    def _warn_hall_once(self, message: str) -> None:
        if message == self._last_hall_error:
            return
        self._last_hall_error = message
        print(message)

    def _format_distance_cm(self, raw_cm: Any, valid: bool) -> str:
        if not valid:
            return "INVALID"
        return "{:d} cm".format(int(round(float(raw_cm))))

    def _normalize_workout_type(self, workout_type: str) -> str:
        get_training_profile(workout_type)
        return normalize_workout_type(workout_type)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
