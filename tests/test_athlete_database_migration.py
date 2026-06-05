"""Tests for athlete account schema migration and backfill."""

from __future__ import annotations

import sqlite3
import unittest

from database_layer.migrations import LEGACY_ATHLETE_EMAIL, run_schema_migrations


class AthleteDatabaseMigrationTest(unittest.TestCase):
    def test_old_rows_are_preserved_and_linked_to_legacy_athlete(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                speed_kmh REAL NOT NULL,
                cadence_rpm INTEGER NOT NULL,
                heart_rate_bpm INTEGER NOT NULL,
                temperature_c REAL NOT NULL,
                left_distance_m REAL NOT NULL,
                right_distance_m REAL NOT NULL,
                display_active INTEGER NOT NULL,
                display_message TEXT NOT NULL,
                speaker_message TEXT NOT NULL,
                alert_level TEXT NOT NULL,
                alert_side TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                status TEXT NOT NULL
            );
            CREATE TABLE decision_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                workout_type TEXT,
                decision_type TEXT NOT NULL,
                alert_level TEXT NOT NULL,
                alert_side TEXT,
                display_active INTEGER NOT NULL DEFAULT 0,
                display_message TEXT,
                speaker_message TEXT,
                recommended_action TEXT,
                source_topic TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE session_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                average_speed_kmh REAL NOT NULL,
                average_cadence_rpm REAL NOT NULL,
                average_heart_rate_bpm REAL NOT NULL,
                max_heart_rate_bpm INTEGER NOT NULL,
                min_heart_rate_bpm INTEGER NOT NULL,
                total_readings INTEGER NOT NULL,
                session_duration_seconds INTEGER NOT NULL,
                time_in_zone_easy INTEGER NOT NULL,
                time_in_zone_moderate INTEGER NOT NULL,
                time_in_zone_hard INTEGER NOT NULL,
                time_in_zone_peak INTEGER NOT NULL,
                improvement_message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE session_report_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                workout_type TEXT,
                email_status TEXT NOT NULL,
                email_to TEXT,
                report_subject TEXT NOT NULL,
                report_body TEXT NOT NULL,
                error_message TEXT,
                generated_at TEXT NOT NULL,
                sent_at TEXT
            );
            CREATE TABLE mqtt_status_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL
            );
            CREATE TABLE session_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                device_id TEXT,
                workout_type TEXT,
                mode TEXT,
                athlete_name TEXT,
                athlete_age INTEGER,
                athlete_weight_kg REAL,
                athlete_height_cm REAL,
                athlete_email TEXT,
                athlete_json TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device_id TEXT,
                session_id TEXT,
                alert_type TEXT NOT NULL,
                alert_level TEXT NOT NULL,
                message TEXT NOT NULL,
                action TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO sessions (session_id, device_id, start_time, status)
            VALUES ('session_old', 'bike_001', '2026-05-26T10:00:00', 'stopped')
            """
        )
        connection.execute(
            """
            INSERT INTO sensor_readings (
                device_id, session_id, timestamp, speed_kmh, cadence_rpm,
                heart_rate_bpm, temperature_c, left_distance_m, right_distance_m,
                display_active, display_message, speaker_message, alert_level,
                alert_side, received_at
            )
            VALUES (
                'bike_001', 'session_old', '2026-05-26T10:00:00', 12.0, 70,
                120, 25.0, 2.0, 2.0, 0, '', '', 'normal', 'none',
                '2026-05-26T10:00:01'
            )
            """
        )

        run_schema_migrations(connection)

        legacy = connection.execute(
            """
            SELECT id
            FROM athletes
            WHERE email = ?
            """,
            (LEGACY_ATHLETE_EMAIL,),
        ).fetchone()
        self.assertIsNotNone(legacy)
        session = connection.execute("SELECT athlete_id FROM sessions").fetchone()
        reading = connection.execute("SELECT athlete_id FROM sensor_readings").fetchone()
        self.assertEqual(session["athlete_id"], legacy["id"])
        self.assertEqual(reading["athlete_id"], legacy["id"])


if __name__ == "__main__":
    unittest.main()
