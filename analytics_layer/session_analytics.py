"""Calculate session-level analytics from stored sensor readings.

This module turns raw sensor rows into ride summaries that are easy to print,
store, or compare with an earlier ride.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from analytics_layer.improvement_analyzer import compare_session_performance
from database_layer.db_connection import get_db_connection


HEART_RATE_ZONES = {
    "easy": (None, 120),
    "moderate": (120, 150),
    "hard": (150, 170),
    "peak": (170, None),
}


def calculate_latest_session_analytics(
    athlete_id: int | None = None,
) -> dict[str, Any] | None:
    """Calculate analytics for the latest session with stored readings."""
    # A dashboard can ask for the latest ride without knowing the session ID.
    latest_session_id = get_latest_session_id(athlete_id=athlete_id)
    if latest_session_id is None:
        return None

    return calculate_session_analytics(latest_session_id)


def calculate_session_analytics(session_id: str) -> dict[str, Any]:
    """Calculate analytics for one session_id and compare with the previous session."""
    # Build the current summary first, then add athlete and comparison context.
    readings = load_readings_for_session(session_id)
    current_analytics = calculate_analytics_from_readings(session_id, readings)
    athlete_id = _get_athlete_id_for_session(session_id)
    current_analytics["athlete_id"] = athlete_id

    previous_session_id = get_previous_session_id(
        session_id,
        athlete_id=athlete_id,
    )
    previous_analytics = None
    if previous_session_id is not None:
        # The previous ride is calculated from readings, not from cached summaries.
        previous_analytics = calculate_analytics_from_readings(
            previous_session_id,
            load_readings_for_session(previous_session_id),
        )

    comparison = compare_session_performance(current_analytics, previous_analytics)
    current_analytics["previous_session_id"] = previous_session_id
    current_analytics["improvement_vs_previous_session"] = comparison["message"]
    current_analytics["improvement_details"] = comparison
    return current_analytics


def calculate_analytics_from_readings(
    session_id: str,
    readings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate basic analytics from already-loaded readings."""
    if not readings:
        return _empty_analytics(session_id)

    # Store numbers as simple rounded values because they are shown in reports.
    speeds = [float(reading["speed_kmh"]) for reading in readings]
    cadences = [int(reading["cadence_rpm"]) for reading in readings]
    heart_rates = [int(reading["heart_rate_bpm"]) for reading in readings]
    sample_seconds = _estimate_sample_seconds(readings)
    zone_counts = _count_heart_rate_zones(heart_rates)

    return {
        "session_id": session_id,
        "average_speed_kmh": round(mean(speeds), 1),
        "average_cadence_rpm": round(mean(cadences), 1),
        "average_heart_rate_bpm": round(mean(heart_rates), 1),
        "max_heart_rate_bpm": max(heart_rates),
        "min_heart_rate_bpm": min(heart_rates),
        "total_readings": len(readings),
        "session_duration_seconds": _calculate_duration_seconds(
            readings,
            sample_seconds,
        ),
        "time_in_zone_easy": int(zone_counts["easy"] * sample_seconds),
        "time_in_zone_moderate": int(zone_counts["moderate"] * sample_seconds),
        "time_in_zone_hard": int(zone_counts["hard"] * sample_seconds),
        "time_in_zone_peak": int(zone_counts["peak"] * sample_seconds),
        "improvement_vs_previous_session": "Not enough previous data",
    }


def load_readings_for_session(session_id: str) -> list[dict[str, Any]]:
    """Load sensor readings for one session_id ordered oldest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sensor_readings
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_latest_session_id(athlete_id: int | None = None) -> str | None:
    """Return the newest session_id that has stored sensor readings."""
    session_ids = list_session_ids_newest_first(athlete_id=athlete_id)
    return session_ids[0] if session_ids else None


def get_previous_session_id(
    current_session_id: str,
    athlete_id: int | None = None,
) -> str | None:
    """Return the session before current_session_id based on stored readings."""
    scoped_athlete_id = (
        athlete_id
        if athlete_id is not None
        else _get_athlete_id_for_session(current_session_id)
    )
    session_ids = list_session_ids_newest_first(athlete_id=scoped_athlete_id)
    try:
        current_index = session_ids.index(current_session_id)
    except ValueError:
        return None

    previous_index = current_index + 1
    if previous_index >= len(session_ids):
        return None

    return session_ids[previous_index]


def list_session_ids_newest_first(athlete_id: int | None = None) -> list[str]:
    """Return session_ids ordered by their latest stored reading."""
    with get_db_connection() as connection:
        if athlete_id is None:
            # Use MAX(id) because inserted reading order is the most reliable order.
            rows = connection.execute(
                """
                SELECT session_id, MAX(id) AS latest_reading_id
                FROM sensor_readings
                WHERE session_id IS NOT NULL AND session_id != ''
                GROUP BY session_id
                ORDER BY latest_reading_id DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT session_id, MAX(id) AS latest_reading_id
                FROM sensor_readings
                WHERE session_id IS NOT NULL
                  AND session_id != ''
                  AND athlete_id = ?
                GROUP BY session_id
                ORDER BY latest_reading_id DESC
                """,
                (int(athlete_id),),
            ).fetchall()

    return [str(row["session_id"]) for row in rows]


def get_athlete_analytics(
    athlete_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return saved analytics summaries for one athlete."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM session_analytics
            WHERE athlete_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(athlete_id), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def _empty_analytics(session_id: str) -> dict[str, Any]:
    """Return the report shape for a session with no sensor readings."""
    return {
        "session_id": session_id,
        "athlete_id": _get_athlete_id_for_session(session_id),
        "average_speed_kmh": 0.0,
        "average_cadence_rpm": 0.0,
        "average_heart_rate_bpm": 0.0,
        "max_heart_rate_bpm": 0,
        "min_heart_rate_bpm": 0,
        "total_readings": 0,
        "session_duration_seconds": 0,
        "time_in_zone_easy": 0,
        "time_in_zone_moderate": 0,
        "time_in_zone_hard": 0,
        "time_in_zone_peak": 0,
        "improvement_vs_previous_session": "Not enough previous data",
    }


def _count_heart_rate_zones(heart_rates: list[int]) -> dict[str, int]:
    """Count how many samples landed in each heart-rate zone."""
    zone_counts = {
        "easy": 0,
        "moderate": 0,
        "hard": 0,
        "peak": 0,
    }

    for heart_rate in heart_rates:
        zone_counts[_get_heart_rate_zone(heart_rate)] += 1

    return zone_counts


def _get_heart_rate_zone(heart_rate_bpm: int) -> str:
    """Map a heart-rate value into the report's simple effort buckets."""
    if heart_rate_bpm < 120:
        return "easy"
    if heart_rate_bpm < 150:
        return "moderate"
    if heart_rate_bpm < 170:
        return "hard"
    return "peak"


def _estimate_sample_seconds(readings: list[dict[str, Any]]) -> int:
    """Estimate the sampling interval from timestamps, defaulting to 1 second."""
    timestamps = _parse_reading_timestamps(readings)
    intervals = [
        int((timestamps[index] - timestamps[index - 1]).total_seconds())
        for index in range(1, len(timestamps))
        if timestamps[index] > timestamps[index - 1]
    ]
    if not intervals:
        return 1

    return max(1, round(mean(intervals)))


def _calculate_duration_seconds(
    readings: list[dict[str, Any]],
    sample_seconds: int,
) -> int:
    """Return the best duration estimate from timestamps and sample count."""
    timestamps = _parse_reading_timestamps(readings)
    elapsed_seconds = 0
    if len(timestamps) >= 2:
        elapsed_seconds = int((timestamps[-1] - timestamps[0]).total_seconds())

    estimated_seconds = len(readings) * sample_seconds
    return max(elapsed_seconds, estimated_seconds)


def _parse_reading_timestamps(readings: list[dict[str, Any]]) -> list[datetime]:
    """Parse valid reading timestamps and ignore malformed ones."""
    timestamps = []
    for reading in readings:
        parsed_timestamp = _parse_timestamp(str(reading.get("timestamp", "")))
        if parsed_timestamp is not None:
            timestamps.append(parsed_timestamp)

    return timestamps


def _parse_timestamp(timestamp: str) -> datetime | None:
    """Parse one ISO timestamp, returning None when it is not valid."""
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return None


def _get_athlete_id_for_session(session_id: str) -> int | None:
    """Find the athlete linked to a session from any table that has it."""
    with get_db_connection() as connection:
        for table in ("sessions", "sensor_readings", "decision_logs"):
            row = connection.execute(
                f"""
                SELECT athlete_id
                FROM {table}
                WHERE session_id = ?
                  AND athlete_id IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            if row is not None:
                return int(row["athlete_id"])
    return None
