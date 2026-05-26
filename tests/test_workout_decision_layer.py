"""Tests for workout-specific backend guidance decisions."""

from __future__ import annotations

import unittest

from ai_decision_layer.decision_engine import DecisionEngine
from backend_layer.backend_service import build_feedback_command


class WorkoutDecisionLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DecisionEngine(rider_profile={"age": 20})

    def test_speed_low_speed_gives_increase_speed(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="speed",
                speed_kmh=6.0,
                cadence_rpm=80,
                heart_rate_bpm=120,
            )
        )

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertEqual(decision.recommended_action, "increase_speed")
        self.assertEqual(decision.lcd_line_1, "SPEED")
        self.assertEqual(decision.lcd_line_2, "Increase speed")
        self.assertFalse(decision.buzzer_state)

    def test_cadence_low_cadence_gives_pedal_faster(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="cadence",
                speed_kmh=12.0,
                cadence_rpm=45,
                heart_rate_bpm=120,
            )
        )

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertEqual(decision.recommended_action, "pedal_faster")
        self.assertEqual(decision.lcd_line_1, "CADENCE")
        self.assertEqual(decision.lcd_line_2, "Pedal faster")

    def test_endurance_target_hr_gives_maintain_pace(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="endurance",
                speed_kmh=14.0,
                cadence_rpm=78,
                heart_rate_bpm=120,
            )
        )
        command = build_feedback_command(decision)

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertEqual(decision.recommended_action, "maintain_pace")
        self.assertEqual(decision.lcd_line_1, "ENDURANCE")
        self.assertEqual(decision.lcd_line_2, "Maintain pace")
        self.assertEqual(decision.hr_percent, 0.6)
        self.assertEqual(command["command"], "update_feedback")
        self.assertEqual(command["decision_type"], "workout_guidance")
        self.assertEqual(command["lcd_line_1"], "ENDURANCE")
        self.assertEqual(command["lcd_line_2"], "Maintain pace")
        self.assertFalse(command["buzzer_state"])
        self.assertEqual(command["heart_rate_bpm"], 120)
        self.assertEqual(command["hr_percent"], 0.6)

    def test_vo2_max_high_hr_gives_recover_now(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="vo2_max",
                speed_kmh=24.0,
                cadence_rpm=95,
                heart_rate_bpm=185,
            )
        )

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertEqual(decision.recommended_action, "recover_now")
        self.assertEqual(decision.lcd_line_1, "VO2 MAX")
        self.assertEqual(decision.lcd_line_2, "Recover now")
        self.assertEqual(decision.hr_percent, 0.925)

    def test_missing_hr_gives_hr_unavailable(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="endurance",
                speed_kmh=14.0,
                cadence_rpm=78,
                heart_rate_bpm=0,
            )
        )
        command = build_feedback_command(decision)

        self.assertEqual(decision.decision_type, "workout_guidance")
        self.assertEqual(decision.recommended_action, "hr_unavailable")
        self.assertEqual(decision.lcd_line_2, "HR unavailable")
        self.assertEqual(command["heart_rate_bpm"], 0)
        self.assertNotIn("hr_percent", command)

    def test_physical_safety_warning_overrides_workout_guidance(self) -> None:
        decision = self.engine.analyze(
            _make_sensor_message(
                workout_type="speed",
                speed_kmh=5.0,
                cadence_rpm=50,
                heart_rate_bpm=120,
                left_distance_m=0.49,
            )
        )

        self.assertEqual(decision.decision_type, "physical_safety")
        self.assertEqual(decision.recommended_action, "object_left")
        self.assertEqual(decision.lcd_line_1, "WARNING LEFT")
        self.assertTrue(decision.buzzer_state)


def _make_sensor_message(
    workout_type: str,
    speed_kmh: float,
    cadence_rpm: int,
    heart_rate_bpm: int,
    left_distance_m: float = 2.0,
    right_distance_m: float = 2.0,
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
        "left_distance_m": left_distance_m,
        "right_distance_m": right_distance_m,
        "display_active": False,
        "display_message": "",
        "speaker_message": "",
        "alert_level": "normal",
        "alert_side": "none",
    }


if __name__ == "__main__":
    unittest.main()
