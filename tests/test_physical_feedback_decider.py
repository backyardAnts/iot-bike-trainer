"""Tests for physical GrovePi feedback decisions."""

from __future__ import annotations

import unittest

from ai_decision_layer.decision_engine import DecisionEngine
from ai_decision_layer.physical_feedback_decider import decide_physical_feedback
from backend_layer.backend_service import build_feedback_command
from mqtt_layer.command_handler import CommandHandler
from sensor_layer.real_sensors.real_bike import RealBike


def make_sensor_data(left_distance_m: float, right_distance_m: float) -> dict[str, object]:
    return {
        "workout_type": "speed",
        "left_distance_m": left_distance_m,
        "right_distance_m": right_distance_m,
    }


def make_workout_sensor_data(
    workout_type: str,
    cadence_rpm: int,
    speed_kmh: float,
    heart_rate_bpm: int,
) -> dict[str, object]:
    return {
        "device_id": "bike_001",
        "timestamp": "test",
        "session_id": "session_001",
        "workout_type": workout_type,
        "speed_kmh": speed_kmh,
        "cadence_rpm": cadence_rpm,
        "heart_rate_bpm": heart_rate_bpm,
        "temperature_c": 25.0,
        "left_distance_m": 2.0,
        "right_distance_m": 2.0,
        "display_active": False,
        "display_message": "",
        "speaker_message": "",
        "alert_level": "normal",
        "alert_side": "none",
    }


class PhysicalFeedbackDeciderTest(unittest.TestCase):
    def test_no_object_close_is_safe(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(0.50, 0.50))

        self.assertEqual(decision["alert_level"], "normal")
        self.assertEqual(decision["warning_side"], "none")
        self.assertFalse(decision["buzzer_state"])
        self.assertEqual(decision["lcd_line_1"], "SAFE")
        self.assertEqual(decision["lcd_line_2"], "No object close")

    def test_left_object_below_50_cm_warns_left(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(0.49, 1.00))

        self.assertEqual(decision["alert_level"], "warning")
        self.assertEqual(decision["warning_side"], "left")
        self.assertTrue(decision["buzzer_state"])
        self.assertEqual(decision["lcd_line_1"], "WARNING LEFT")

    def test_right_object_below_50_cm_warns_right(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(1.00, 0.49))

        self.assertEqual(decision["alert_level"], "warning")
        self.assertEqual(decision["warning_side"], "right")
        self.assertTrue(decision["buzzer_state"])
        self.assertEqual(decision["lcd_line_1"], "WARNING RIGHT")

    def test_both_objects_below_50_cm_warns_both(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(0.49, 0.49))

        self.assertEqual(decision["alert_level"], "danger")
        self.assertEqual(decision["warning_side"], "both")
        self.assertTrue(decision["buzzer_state"])
        self.assertEqual(decision["lcd_line_1"], "WARNING BOTH")

    def test_backend_command_includes_physical_output_fields(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(0.49, 1.00))
        command = build_feedback_command(decision)

        self.assertEqual(command["command"], "update_feedback")
        self.assertTrue(command["buzzer_state"])
        self.assertEqual(command["buzzer_pulse_ms"], 0)
        self.assertEqual(command["buzzer_pulse_reason"], "")
        self.assertEqual(command["lcd_line_1"], "WARNING LEFT")
        self.assertEqual(command["warning_side"], "left")

    def test_command_handler_uses_physical_feedback_api(self) -> None:
        decision = decide_physical_feedback(make_sensor_data(1.00, 0.49))
        command = build_feedback_command(decision)
        bike = _FakeRealBike()

        result = CommandHandler(bike).handle_command(command)

        self.assertTrue(result["ok"])
        self.assertEqual(bike.last_command["lcd_line_1"], "WARNING RIGHT")
        self.assertTrue(bike.last_command["buzzer_state"])

    def test_command_handler_preserves_buzzer_pulse_fields(self) -> None:
        command = _make_workout_command(
            workout_type="speed",
            cadence_rpm=70,
            speed_kmh=0.0,
            heart_rate_bpm=200,
        )
        bike = _FakeRealBike()

        result = CommandHandler(bike).handle_command(command)

        self.assertTrue(result["ok"])
        self.assertEqual(result["buzzer_pulse_ms"], 500)
        self.assertEqual(result["buzzer_pulse_reason"], "hr_warning")
        self.assertEqual(bike.last_command["buzzer_pulse_ms"], 500)

    def test_deferred_command_handler_does_not_apply_physical_command_in_callback(
        self,
    ) -> None:
        decision = decide_physical_feedback(make_sensor_data(1.00, 0.49))
        command = build_feedback_command(decision)
        bike = _FakeRealBike()
        handler = CommandHandler(bike, defer_application=True)

        result = handler.handle_command(command)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "queued")
        self.assertEqual(bike.last_command, {})

        apply_result = handler.apply_latest_command()

        self.assertIsNotNone(apply_result)
        self.assertTrue(apply_result["ok"])
        self.assertEqual(bike.last_command["lcd_line_1"], "WARNING RIGHT")
        self.assertTrue(bike.last_command["buzzer_state"])

    def test_real_bike_falls_back_without_command_feedback(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=False)

        self.assertTrue(bike._should_use_local_feedback_fallback())

    def test_real_bike_command_applies_buzzer_and_lcd(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 1.00))
        )

        bike.apply_physical_feedback_command(command)

        self.assertFalse(bike._should_use_local_feedback_fallback())
        self.assertTrue(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("WARNING LEFT", "Object close"))

    def test_real_bike_backend_safe_command_does_not_write_safe_lcd(
        self,
    ) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        warning_command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 1.00))
        )
        safe_command = {
            "command": "update_feedback",
            "display_active": False,
            "display_message": "SAFE",
            "speaker_message": "",
            "alert_level": "normal",
            "alert_side": "none",
            "buzzer_state": False,
            "decision_type": "physical_safety",
            "recommended_action": "safe",
        }

        bike.apply_physical_feedback_command(warning_command)
        bike.apply_physical_feedback_command(safe_command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertNotEqual(bike.lcd.last_message, ("SAFE", "No object close"))

    def test_real_bike_does_not_rewrite_unchanged_lcd_lines(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 1.00))
        )

        bike.apply_physical_feedback_command(command)
        bike.apply_physical_feedback_command(command)

        self.assertEqual(bike.lcd.display_count, 1)

    def test_real_bike_workout_guidance_updates_lcd_without_buzzer(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        decision = DecisionEngine(rider_profile={"age": 20}).analyze(
            make_workout_sensor_data(
                workout_type="cadence",
                cadence_rpm=45,
                speed_kmh=12.0,
                heart_rate_bpm=120,
            )
        )
        command = build_feedback_command(decision)

        bike.apply_physical_feedback_command(command)

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("SPD 12.0 HR 120", "Pedal faster"))
        self.assertEqual(bike.buzzer.beep_durations, [])

    def test_real_bike_urgent_workout_guidance_pulses_buzzer_once(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = _make_workout_command(
            workout_type="speed",
            cadence_rpm=70,
            speed_kmh=0.0,
            heart_rate_bpm=200,
        )

        bike.apply_physical_feedback_command(command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.buzzer.beep_durations, [0.5])
        self.assertEqual(bike.lcd.last_message, ("SPD 0.0 HR 200", "Recover now"))

    def test_real_bike_duplicate_urgent_workout_command_respects_cooldown(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = _make_workout_command(
            workout_type="speed",
            cadence_rpm=70,
            speed_kmh=0.0,
            heart_rate_bpm=200,
        )

        bike.apply_physical_feedback_command(command)
        bike.apply_physical_feedback_command(command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.buzzer.beep_durations, [0.5])

    def test_deferred_handler_applies_workout_pulse_from_main_loop_path(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = _make_workout_command(
            workout_type="cadence",
            cadence_rpm=0,
            speed_kmh=0.0,
            heart_rate_bpm=200,
        )
        handler = CommandHandler(bike, defer_application=True)

        result = handler.handle_command(command)

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["buzzer_pulse_ms"], 500)
        self.assertEqual(bike.buzzer.beep_durations, [])

        apply_result = handler.apply_latest_command()

        self.assertIsNotNone(apply_result)
        self.assertTrue(apply_result["ok"])
        self.assertEqual(bike.buzzer.beep_durations, [0.5])

    def test_real_bike_physical_warning_does_not_use_workout_pulse(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        warning_command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 2.00))
        )

        bike.apply_physical_feedback_command(warning_command)

        self.assertTrue(bike.buzzer.enabled)
        self.assertEqual(bike.buzzer.beep_durations, [])
        self.assertEqual(warning_command["buzzer_pulse_ms"], 0)

    def test_real_bike_safe_command_keeps_latest_workout_guidance(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        workout_command = _make_workout_command(
            workout_type="cadence",
            cadence_rpm=84,
            speed_kmh=12.0,
            heart_rate_bpm=132,
        )
        safe_command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(2.00, 2.00))
        )

        bike.apply_physical_feedback_command(workout_command)
        bike.apply_physical_feedback_command(safe_command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("SPD 12.0 HR 132", "Keep cadence"))

    def test_real_bike_physical_warning_overrides_workout_guidance(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        workout_command = _make_workout_command(
            workout_type="cadence",
            cadence_rpm=84,
            speed_kmh=12.0,
            heart_rate_bpm=132,
        )
        warning_command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 2.00))
        )

        bike.apply_physical_feedback_command(workout_command)
        bike.apply_physical_feedback_command(warning_command)

        self.assertTrue(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("WARNING LEFT", "Object close"))

    def test_real_bike_returns_to_workout_guidance_after_warning(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        workout_command = _make_workout_command(
            workout_type="cadence",
            cadence_rpm=84,
            speed_kmh=12.0,
            heart_rate_bpm=132,
        )
        warning_command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 2.00))
        )

        bike.apply_physical_feedback_command(workout_command)
        bike.apply_physical_feedback_command(warning_command)
        bike.apply_physical_feedback_command(workout_command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("SPD 12.0 HR 132", "Keep cadence"))
        self.assertNotEqual(bike.lcd.last_message, ("SAFE", "No object close"))

    def test_real_bike_backend_mode_update_does_not_write_local_safe(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        bike.apply_physical_feedback_command(
            _make_workout_command(
                workout_type="cadence",
                cadence_rpm=84,
                speed_kmh=12.0,
                heart_rate_bpm=132,
            )
        )

        bike.update()

        self.assertEqual(bike.lcd.last_message, ("SPD 12.0 HR 132", "Keep cadence"))

    def test_real_bike_local_fallback_still_shows_safe(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=False)

        bike.update()

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("SAFE", "No object close"))


class _FakeRealBike:
    def __init__(self) -> None:
        self.last_command = {}

    def apply_physical_feedback_command(self, command_data: dict[str, object]) -> None:
        self.last_command = dict(command_data)


class _FakeBuzzer:
    def __init__(self) -> None:
        self.enabled = False
        self.beep_durations = []

    def set_state(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def beep(self, duration: float = 0.2) -> None:
        self.beep_durations.append(float(duration))
        self.enabled = False


class _FakeLcd:
    def __init__(self) -> None:
        self.last_message = ("", "")
        self.display_count = 0

    def display(self, line1: str, line2: str = "") -> None:
        self.last_message = (line1, line2)
        self.display_count += 1


class _FakeUltrasonicSensors:
    def read(self) -> tuple[float, float]:
        return (2.0, 2.0)

    def get_last_status(self) -> dict[str, object]:
        return {
            "left_raw_cm": 200,
            "left_valid": True,
            "right_raw_cm": 200,
            "right_valid": True,
        }


def _make_workout_command(
    workout_type: str,
    cadence_rpm: int,
    speed_kmh: float,
    heart_rate_bpm: int,
) -> dict[str, object]:
    decision = DecisionEngine(rider_profile={"age": 20}).analyze(
        make_workout_sensor_data(
            workout_type=workout_type,
            cadence_rpm=cadence_rpm,
            speed_kmh=speed_kmh,
            heart_rate_bpm=heart_rate_bpm,
        )
    )
    return build_feedback_command(decision)


def _make_fake_real_bike(command_feedback_enabled: bool) -> RealBike:
    bike = object.__new__(RealBike)
    bike.device_id = "bike_001"
    bike.session_id = "session_test"
    bike.workout_type = "speed"
    bike.heart_rate_bpm = 0
    bike.hall_debug = False
    bike.temperature_debug = False
    bike.hall_sensors = None
    bike.temperature_sensor = None
    bike.ultrasonic_sensors = _FakeUltrasonicSensors()
    bike.command_feedback_enabled = command_feedback_enabled
    bike.command_timeout_seconds = 3.0
    bike._last_command_time = None
    bike._latest_message = None
    bike._latest_status = ""
    bike._latest_humidity_percent = None
    bike._last_hall_error = ""
    bike._last_temperature_error = ""
    bike.buzzer = _FakeBuzzer()
    bike.lcd = _FakeLcd()
    bike._latest_feedback = bike._build_safe_feedback()
    bike._latest_workout_feedback = None
    bike._last_lcd_lines = None
    bike._last_workout_buzzer_pulse_time = None
    bike._last_workout_buzzer_pulse_action = ""
    return bike


if __name__ == "__main__":
    unittest.main()
