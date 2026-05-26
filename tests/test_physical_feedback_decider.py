"""Tests for physical GrovePi feedback decisions."""

from __future__ import annotations

import unittest

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

    def test_real_bike_safe_backend_command_updates_lcd_when_display_inactive(
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
        }

        bike.apply_physical_feedback_command(warning_command)
        bike.apply_physical_feedback_command(safe_command)

        self.assertFalse(bike.buzzer.enabled)
        self.assertEqual(bike.lcd.last_message, ("SAFE", "No object close"))

    def test_real_bike_does_not_rewrite_unchanged_lcd_lines(self) -> None:
        bike = _make_fake_real_bike(command_feedback_enabled=True)
        command = build_feedback_command(
            decide_physical_feedback(make_sensor_data(0.49, 1.00))
        )

        bike.apply_physical_feedback_command(command)
        bike.apply_physical_feedback_command(command)

        self.assertEqual(bike.lcd.display_count, 1)


class _FakeRealBike:
    def __init__(self) -> None:
        self.last_command = {}

    def apply_physical_feedback_command(self, command_data: dict[str, object]) -> None:
        self.last_command = dict(command_data)


class _FakeBuzzer:
    def __init__(self) -> None:
        self.enabled = False

    def set_state(self, enabled: bool) -> None:
        self.enabled = bool(enabled)


class _FakeLcd:
    def __init__(self) -> None:
        self.last_message = ("", "")
        self.display_count = 0

    def display(self, line1: str, line2: str = "") -> None:
        self.last_message = (line1, line2)
        self.display_count += 1


def _make_fake_real_bike(command_feedback_enabled: bool) -> RealBike:
    bike = object.__new__(RealBike)
    bike.workout_type = "speed"
    bike.command_feedback_enabled = command_feedback_enabled
    bike.command_timeout_seconds = 3.0
    bike._last_command_time = None
    bike.buzzer = _FakeBuzzer()
    bike.lcd = _FakeLcd()
    bike._latest_feedback = bike._build_safe_feedback()
    bike._last_lcd_lines = None
    return bike


if __name__ == "__main__":
    unittest.main()
