"""Run a simple session analytics report from stored SQLite readings.

This script is meant for quick checks after a ride: it loads one session from
SQLite, calculates the summary numbers, prints them, and can store the result.
"""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from analytics_layer.session_analytics import (
    calculate_session_analytics,
    get_latest_session_id,
)
from database_layer.db_connection import SCHEMA_PATH, initialize_database
from database_layer.sqlite_storage import save_session_analytics


def run_session_analytics(
    session_id: str | None = None,
    save_summary: bool = True,
) -> dict[str, Any] | None:
    """Calculate, print, and optionally save analytics for one session."""
    # The report reads from SQLite, so make sure the schema exists first.
    initialize_database()

    # If no session is passed on the command line, use the latest stored ride.
    selected_session_id = session_id or get_latest_session_id()
    if selected_session_id is None:
        print("No sensor readings found. Run the simulator/backend first.")
        return None

    # Empty sessions are still returned so callers can see which ID was checked.
    analytics = calculate_session_analytics(selected_session_id)
    if analytics["total_readings"] == 0:
        print(f"No readings found for session: {selected_session_id}")
        return analytics

    print_session_analytics(analytics)
    if save_summary:
        save_session_analytics(analytics)
        print("Saved session analytics summary.")

    return analytics


def print_session_analytics(analytics: dict[str, Any]) -> None:
    """Print a readable analytics summary."""
    # Keep this output plain because it is used from the terminal.
    print("Session Analytics")
    print(f"Session: {analytics['session_id']}")
    print(f"Average speed: {analytics['average_speed_kmh']} km/h")
    print(f"Average cadence: {analytics['average_cadence_rpm']} rpm")
    print(f"Average heart rate: {analytics['average_heart_rate_bpm']} bpm")
    print(f"Max heart rate: {analytics['max_heart_rate_bpm']} bpm")
    print(f"Min heart rate: {analytics['min_heart_rate_bpm']} bpm")
    print(f"Total readings: {analytics['total_readings']}")
    print(f"Duration: {analytics['session_duration_seconds']} seconds")
    print(f"Time in easy zone: {analytics['time_in_zone_easy']} seconds")
    print(f"Time in moderate zone: {analytics['time_in_zone_moderate']} seconds")
    print(f"Time in hard zone: {analytics['time_in_zone_hard']} seconds")
    print(f"Time in peak zone: {analytics['time_in_zone_peak']} seconds")
    print(f"Improvement: {analytics['improvement_vs_previous_session']}")


def run_self_test() -> None:
    """Run analytics checks against a temporary SQLite database."""
    from analytics_layer import session_analytics as analytics_module
    from database_layer import sqlite_storage

    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "analytics_test.db"

        def get_test_db_connection() -> sqlite3.Connection:
            """Open the temporary database used only for this self-test."""
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            return connection

        # Build a fresh schema so the test does not touch the real project data.
        with get_test_db_connection() as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        # Patch the storage modules to use the temporary database connection.
        original_analytics_connection = analytics_module.get_db_connection
        original_storage_connection = sqlite_storage.get_db_connection
        analytics_module.get_db_connection = get_test_db_connection
        sqlite_storage.get_db_connection = get_test_db_connection
        try:
            _insert_demo_readings(sqlite_storage)
            analytics = analytics_module.calculate_session_analytics("session_new")
            sqlite_storage.save_session_analytics(analytics)
        finally:
            analytics_module.get_db_connection = original_analytics_connection
            sqlite_storage.get_db_connection = original_storage_connection

        # These checks lock down the exact values produced by the demo readings.
        if analytics["average_speed_kmh"] != 24.0:
            raise RuntimeError(f"Unexpected average speed: {analytics}")
        if analytics["average_cadence_rpm"] != 82.0:
            raise RuntimeError(f"Unexpected average cadence: {analytics}")
        if analytics["average_heart_rate_bpm"] != 143.8:
            raise RuntimeError(f"Unexpected average heart rate: {analytics}")
        if analytics["max_heart_rate_bpm"] != 175:
            raise RuntimeError(f"Unexpected max heart rate: {analytics}")
        if analytics["min_heart_rate_bpm"] != 110:
            raise RuntimeError(f"Unexpected min heart rate: {analytics}")
        if analytics["time_in_zone_easy"] != 1:
            raise RuntimeError(f"Unexpected easy zone time: {analytics}")
        if analytics["time_in_zone_moderate"] != 1:
            raise RuntimeError(f"Unexpected moderate zone time: {analytics}")
        if analytics["time_in_zone_hard"] != 1:
            raise RuntimeError(f"Unexpected hard zone time: {analytics}")
        if analytics["time_in_zone_peak"] != 1:
            raise RuntimeError(f"Unexpected peak zone time: {analytics}")
        if analytics["improvement_vs_previous_session"] != "Performance improved":
            raise RuntimeError(f"Unexpected improvement message: {analytics}")

        with get_test_db_connection() as connection:
            saved_count = connection.execute(
                "SELECT COUNT(*) AS count FROM session_analytics"
            ).fetchone()["count"]

        if saved_count != 1:
            raise RuntimeError("Session analytics summary was not saved.")

    print("Session analytics self-test passed.")


def _insert_demo_readings(sqlite_storage_module: Any) -> None:
    """Insert two small sessions so improvement comparison can be tested."""
    for session_id, readings in {
        "session_old": [
            (20.0, 78, 125),
            (21.0, 80, 140),
            (22.0, 82, 150),
            (21.0, 80, 153),
        ],
        "session_new": [
            (22.0, 80, 110),
            (24.0, 82, 130),
            (25.0, 83, 160),
            (25.0, 83, 175),
        ],
    }.items():
        for index, reading in enumerate(readings):
            speed_kmh, cadence_rpm, heart_rate_bpm = reading
            sqlite_storage_module.save_sensor_reading(
                _build_test_sensor_message(
                    session_id=session_id,
                    timestamp=f"2026-01-01T00:00:0{index}",
                    speed_kmh=speed_kmh,
                    cadence_rpm=cadence_rpm,
                    heart_rate_bpm=heart_rate_bpm,
                )
            )


def _build_test_sensor_message(
    session_id: str,
    timestamp: str,
    speed_kmh: float,
    cadence_rpm: int,
    heart_rate_bpm: int,
) -> dict[str, Any]:
    """Build the same shape of message the simulator writes during a ride."""
    return {
        "device_id": "bike_001",
        "timestamp": timestamp,
        "session_id": session_id,
        "workout_type": "cadence",
        "speed_kmh": speed_kmh,
        "cadence_rpm": cadence_rpm,
        "heart_rate_bpm": heart_rate_bpm,
        "temperature_c": 25.0,
        "left_distance_m": 3.0,
        "right_distance_m": 3.0,
        "display_active": False,
        "display_message": "",
        "speaker_message": "",
        "alert_level": "normal",
        "alert_side": "none",
    }


def parse_args() -> argparse.Namespace:
    """Read the command-line options for the analytics script."""
    parser = argparse.ArgumentParser(description="Session analytics report")
    parser.add_argument(
        "--session",
        help="specific session_id to analyze; defaults to latest session",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="print analytics without saving a summary row",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run a temporary-database analytics self-test",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        run_self_test()
    else:
        run_session_analytics(
            session_id=args.session,
            save_summary=not args.no_save,
        )
