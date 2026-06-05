"""Tests for stopped-session analytics and email reporting."""

from __future__ import annotations

import json
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backend_layer.backend_service as backend_service_module
from analytics_layer import session_report
from analytics_layer.session_report import (
    generate_session_report,
    process_stopped_session_report,
)
from analytics_layer.session_report_email_template import (
    build_session_report_email_content,
)
from backend_layer.backend_service import BackendService
from config_layer.mqtt_topics import STATUS_TOPIC
from database_layer import sqlite_storage
from database_layer.db_connection import SCHEMA_PATH


class SessionReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "session_report_test.db"
        with self._connect() as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.original_report_connection = session_report.get_db_connection
        self.original_storage_connection = sqlite_storage.get_db_connection
        session_report.get_db_connection = self._connect
        sqlite_storage.get_db_connection = self._connect

    def tearDown(self) -> None:
        session_report.get_db_connection = self.original_report_connection
        sqlite_storage.get_db_connection = self.original_storage_connection
        self.temp_dir.cleanup()

    def test_analytics_calculates_speed_cadence_hr_and_distance(self) -> None:
        self._insert_session(
            "session_100",
            "cadence",
            [
                ("2026-05-26T10:00:00", 10.0, 70, 120, "keep_cadence"),
                ("2026-05-26T10:00:10", 20.0, 80, 150, "keep_cadence"),
                ("2026-05-26T10:00:20", 30.0, 90, 180, "recover", "warning"),
            ],
        )

        report = generate_session_report(
            "session_100",
            stopped_status={
                "session_id": "session_100",
                "device_id": "bike_001",
                "workout_type": "cadence",
                "timestamp": "2026-05-26T10:00:30",
            },
        )

        self.assertEqual(report["total_sensor_readings"], 3)
        self.assertEqual(report["duration_seconds"], 30)
        self.assertEqual(report["performance"]["top_speed_kmh"], 30.0)
        self.assertEqual(report["performance"]["avg_speed_kmh"], 20.0)
        self.assertEqual(report["performance"]["top_cadence_rpm"], 90)
        self.assertEqual(report["performance"]["avg_cadence_rpm"], 80.0)
        self.assertEqual(report["performance"]["estimated_distance_km"], 0.167)

    def test_top_and_average_heart_rate_are_correct(self) -> None:
        self._insert_session(
            "session_hr",
            "speed",
            [
                ("2026-05-26T10:00:00", 12.0, 75, 0, "increase_speed"),
                ("2026-05-26T10:00:10", 14.0, 80, 140, "maintain_speed"),
                ("2026-05-26T10:00:20", 16.0, 82, 180, "recover", "warning"),
            ],
        )

        report = generate_session_report("session_hr")

        self.assertEqual(report["performance"]["top_heart_rate_bpm"], 180)
        self.assertEqual(report["performance"]["avg_heart_rate_bpm"], 160.0)

    def test_safety_warning_counts_are_correct(self) -> None:
        self._insert_session(
            "session_safety",
            "cadence",
            [
                (
                    "2026-05-26T10:00:00",
                    10.0,
                    70,
                    120,
                    "object_left",
                    "warning",
                    "left",
                    "physical_safety",
                ),
                (
                    "2026-05-26T10:00:10",
                    10.0,
                    70,
                    125,
                    "object_right",
                    "warning",
                    "right",
                    "physical_safety",
                ),
                (
                    "2026-05-26T10:00:20",
                    10.0,
                    70,
                    130,
                    "object_both",
                    "danger",
                    "both",
                    "physical_safety",
                ),
                (
                    "2026-05-26T10:00:30",
                    10.0,
                    70,
                    190,
                    "recover",
                    "warning",
                    "none",
                    "workout_guidance",
                ),
            ],
        )

        report = generate_session_report("session_safety")

        self.assertEqual(report["safety"]["left_warnings"], 1)
        self.assertEqual(report["safety"]["right_warnings"], 1)
        self.assertEqual(report["safety"]["both_warnings"], 1)
        self.assertEqual(report["safety"]["total_safety_warnings"], 3)
        self.assertEqual(report["safety"]["high_hr_workout_warnings"], 1)

    def test_comparison_uses_only_previous_sessions_of_same_workout_type(self) -> None:
        self._insert_session(
            "session_cadence_old",
            "cadence",
            [("2026-05-26T09:00:00", 10.0, 70, 120, "keep_cadence")],
        )
        self._insert_session(
            "session_speed_old",
            "speed",
            [("2026-05-26T09:10:00", 100.0, 95, 160, "maintain_speed")],
        )
        self._insert_session(
            "session_cadence_new",
            "cadence",
            [("2026-05-26T09:20:00", 20.0, 80, 130, "keep_cadence")],
        )

        report = generate_session_report(
            "session_cadence_new",
            stopped_status={
                "session_id": "session_cadence_new",
                "device_id": "bike_001",
                "workout_type": "cadence",
                "timestamp": "2026-05-26T09:21:00",
            },
        )

        previous = report["comparison"]["previous_session"]
        self.assertEqual(previous["session_id"], "session_cadence_old")
        self.assertEqual(previous["top_speed_kmh_delta"], 10.0)

    def test_comparison_uses_only_same_athlete_sessions(self) -> None:
        athlete_a = sqlite_storage.create_athlete_account(
            "Anthony",
            email="anthony@example.com",
            age=30,
        )
        athlete_b = sqlite_storage.create_athlete_account(
            "Coach",
            email="coach@example.com",
            age=40,
        )
        self._insert_session(
            "session_anthony_old",
            "cadence",
            [("2026-05-26T09:00:00", 10.0, 70, 120, "keep_cadence")],
            athlete_id=athlete_a["id"],
        )
        self._insert_session(
            "session_coach_old",
            "cadence",
            [("2026-05-26T09:10:00", 40.0, 95, 160, "maintain_speed")],
            athlete_id=athlete_b["id"],
        )
        self._insert_session(
            "session_anthony_new",
            "cadence",
            [("2026-05-26T09:20:00", 20.0, 80, 130, "keep_cadence")],
            athlete_id=athlete_a["id"],
        )

        report = generate_session_report(
            "session_anthony_new",
            stopped_status={
                "session_id": "session_anthony_new",
                "device_id": "bike_001",
                "workout_type": "cadence",
                "timestamp": "2026-05-26T09:21:00",
            },
        )

        previous = report["comparison"]["previous_session"]
        self.assertEqual(report["athlete_id"], athlete_a["id"])
        self.assertEqual(previous["session_id"], "session_anthony_old")
        self.assertEqual(previous["top_speed_kmh_delta"], 10.0)

    def test_backend_stopped_status_triggers_email_report_processing(self) -> None:
        calls = []
        original_processor = backend_service_module.process_stopped_session_report
        backend_service_module.process_stopped_session_report = (
            lambda payload: calls.append(dict(payload))
        )
        try:
            service = BackendService()
            service.handle_status_message(
                STATUS_TOPIC,
                json.dumps(
                    {
                        "status": "stopped",
                        "device_id": "bike_001",
                        "session_id": "session_200",
                        "workout_type": "speed",
                        "timestamp": "2026-05-26T11:00:00",
                    }
                ),
            )
        finally:
            backend_service_module.process_stopped_session_report = original_processor

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "session_200")
        self.assertEqual(calls[0]["status"], "stopped")

    def test_duplicate_stopped_status_does_not_send_duplicate_email(self) -> None:
        self._insert_session(
            "session_duplicate",
            "speed",
            [("2026-05-26T10:00:00", 12.0, 75, 140, "maintain_speed")],
        )
        sent_subjects = []

        def fake_email_sender(subject: str, body: str) -> dict[str, object]:
            sent_subjects.append(subject)
            return {
                "status": "sent",
                "sent": True,
                "email_to": "coach@example.com",
                "error": "",
            }

        original_processor = backend_service_module.process_stopped_session_report
        backend_service_module.process_stopped_session_report = (
            lambda payload: process_stopped_session_report(
                payload,
                email_sender=fake_email_sender,
            )
        )
        service = BackendService()
        payload = json.dumps(
            {
                "status": "stopped",
                "device_id": "bike_001",
                "session_id": "session_duplicate",
                "workout_type": "speed",
                "timestamp": "2026-05-26T10:05:00",
            }
        )
        try:
            service.handle_status_message(STATUS_TOPIC, payload)
            service.handle_status_message(STATUS_TOPIC, payload)
        finally:
            backend_service_module.process_stopped_session_report = original_processor

        self.assertEqual(len(sent_subjects), 1)
        with self._connect() as connection:
            report_count = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM session_report_emails
                WHERE session_id = 'session_duplicate'
                """
            ).fetchone()["count"]
        self.assertEqual(report_count, 1)

    def test_session_report_email_content_includes_html_dashboard(self) -> None:
        self._insert_session(
            "session_visual",
            "cadence",
            [
                ("2026-05-26T10:00:00", 10.0, 70, 120, "keep_cadence"),
                ("2026-05-26T10:00:10", 18.0, 82, 145, "pedal_faster"),
                ("2026-05-26T10:00:20", 22.0, 90, 175, "recover", "warning"),
            ],
        )

        report = generate_session_report(
            "session_visual",
            stopped_status={
                "session_id": "session_visual",
                "device_id": "bike_001",
                "workout_type": "cadence",
                "timestamp": "2026-05-26T10:00:30",
            },
        )
        content = build_session_report_email_content(report)

        self.assertIn("Bike Workout Summary", content["text_body"])
        self.assertIn("<html", content["html_body"])
        self.assertIn("IoT Bike Trainer", content["html_body"])
        self.assertIn("Average speed", content["html_body"])
        self.assertIn("Average cadence", content["html_body"])
        self.assertIn("Average heart rate", content["html_body"])
        self.assertIn("Max heart rate", content["html_body"])
        self.assertIn("Estimated distance", content["html_body"])
        self.assertIn("Safety &amp; Feedback", content["html_body"])
        self.assertIn("Notable DecisionEngine outputs", content["html_body"])

    def test_email_sender_receives_html_when_supported(self) -> None:
        self._insert_session(
            "session_html_sender",
            "speed",
            [("2026-05-26T10:00:00", 12.0, 75, 140, "maintain_speed")],
        )
        sent = {}

        def fake_email_sender(
            subject: str,
            body: str,
            html_body: str | None = None,
        ) -> dict[str, object]:
            sent["subject"] = subject
            sent["body"] = body
            sent["html_body"] = html_body
            return {
                "status": "sent",
                "sent": True,
                "email_to": "coach@example.com",
                "error": "",
            }

        result = process_stopped_session_report(
            {
                "session_id": "session_html_sender",
                "device_id": "bike_001",
                "workout_type": "speed",
                "timestamp": "2026-05-26T10:05:00",
            },
            email_sender=fake_email_sender,
        )

        self.assertIsNotNone(result)
        self.assertIn("Bike Workout Summary", str(sent["body"]))
        self.assertIn("<html", str(sent["html_body"]))

    def test_two_argument_email_sender_still_works(self) -> None:
        self._insert_session(
            "session_legacy_sender",
            "cadence",
            [("2026-05-26T10:00:00", 10.0, 70, 120, "keep_cadence")],
        )
        sent_subjects = []

        def fake_email_sender(subject: str, body: str) -> dict[str, object]:
            sent_subjects.append(subject)
            return {
                "status": "sent",
                "sent": True,
                "email_to": "coach@example.com",
                "error": "",
            }

        result = process_stopped_session_report(
            {
                "session_id": "session_legacy_sender",
                "device_id": "bike_001",
                "workout_type": "cadence",
                "timestamp": "2026-05-26T10:05:00",
            },
            email_sender=fake_email_sender,
        )

        self.assertIsNotNone(result)
        self.assertEqual(len(sent_subjects), 1)

    def test_email_disabled_skips_safely(self) -> None:
        self._insert_session(
            "session_disabled",
            "cadence",
            [("2026-05-26T10:00:00", 10.0, 70, 120, "keep_cadence")],
        )

        with patch.dict(os.environ, {"EMAIL_ENABLED": "false"}, clear=False):
            with patch("sys.stdout", new=io.StringIO()):
                result = process_stopped_session_report(
                    {
                        "session_id": "session_disabled",
                        "device_id": "bike_001",
                        "workout_type": "cadence",
                        "timestamp": "2026-05-26T10:05:00",
                    }
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["email"]["status"], "skipped_disabled")

    def test_missing_readings_do_not_crash_report_generation(self) -> None:
        report = generate_session_report(
            "session_empty",
            stopped_status={
                "session_id": "session_empty",
                "device_id": "bike_001",
                "workout_type": "vo2_max",
                "timestamp": "2026-05-26T12:00:00",
            },
        )

        self.assertEqual(report["total_sensor_readings"], 0)
        self.assertEqual(report["performance"]["top_speed_kmh"], 0.0)
        self.assertEqual(report["performance"]["top_heart_rate_bpm"], 0)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _insert_session(
        self,
        session_id: str,
        workout_type: str,
        readings: list[tuple[object, ...]],
        athlete_id: int | None = None,
    ) -> None:
        if readings:
            sqlite_storage.start_session(
                session_id,
                "bike_001",
                str(readings[0][0]),
                athlete_id=athlete_id,
            )
        for index, reading in enumerate(readings):
            timestamp = str(reading[0])
            speed_kmh = float(reading[1])
            cadence_rpm = int(reading[2])
            heart_rate_bpm = int(reading[3])
            recommended_action = str(reading[4])
            alert_level = str(reading[5]) if len(reading) > 5 else "normal"
            alert_side = str(reading[6]) if len(reading) > 6 else "none"
            decision_type = str(reading[7]) if len(reading) > 7 else "workout_guidance"
            sensor_message = {
                "device_id": "bike_001",
                "timestamp": timestamp,
                "session_id": session_id,
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
                "alert_level": alert_level,
                "alert_side": alert_side,
            }
            sqlite_storage.save_sensor_reading(sensor_message)
            sqlite_storage.save_decision_log(
                sensor_message,
                {
                    "workout_type": workout_type,
                    "decision_type": decision_type,
                    "alert_level": alert_level,
                    "alert_side": alert_side,
                    "display_active": alert_level in {"warning", "danger"},
                    "display_message": recommended_action,
                    "speaker_message": "",
                    "recommended_action": recommended_action,
                },
                source_topic="test",
            )


if __name__ == "__main__":
    unittest.main()
