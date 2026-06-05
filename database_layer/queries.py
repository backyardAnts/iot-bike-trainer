"""Read helpers for future dashboard and reporting phases."""

from __future__ import annotations

from typing import Any

from database_layer.db_connection import get_db_connection


INSERT_DECISION_LOG = """
INSERT INTO decision_logs (
    athlete_id,
    device_id,
    session_id,
    timestamp,
    workout_type,
    decision_type,
    alert_level,
    alert_side,
    display_active,
    display_message,
    speaker_message,
    recommended_action,
    source_topic
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_RECENT_DECISION_LOGS = """
SELECT *
FROM decision_logs
ORDER BY id DESC
LIMIT ?
"""

COUNT_DECISIONS_BY_ALERT_LEVEL = """
SELECT alert_level, COUNT(*) AS count
FROM decision_logs
GROUP BY alert_level
ORDER BY alert_level
"""

COUNT_DECISIONS_BY_TYPE = """
SELECT decision_type, COUNT(*) AS count
FROM decision_logs
GROUP BY decision_type
ORDER BY decision_type
"""

INSERT_SESSION_ANALYTICS = """
INSERT INTO session_analytics (
    athlete_id,
    session_id,
    timestamp,
    average_speed_kmh,
    average_cadence_rpm,
    average_heart_rate_bpm,
    max_heart_rate_bpm,
    min_heart_rate_bpm,
    total_readings,
    session_duration_seconds,
    time_in_zone_easy,
    time_in_zone_moderate,
    time_in_zone_hard,
    time_in_zone_peak,
    improvement_message
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

SELECT_RECENT_SESSION_ANALYTICS = """
SELECT *
FROM session_analytics
ORDER BY id DESC
LIMIT ?
"""


def get_latest_reading() -> dict[str, Any] | None:
    """Return the newest sensor reading, or None when no data exists."""
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM sensor_readings
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    return _row_to_dict(row)


def get_recent_readings(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent sensor readings, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sensor_readings
            ORDER BY id DESC
            LIMIT ?
            """,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_command_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent MQTT command messages, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM commands
            ORDER BY id DESC
            LIMIT ?
            """,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_status_history(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent MQTT status messages, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM mqtt_status_messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_session_history(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent training sessions, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sessions
            ORDER BY id DESC
            LIMIT ?
            """,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_settings() -> dict[str, str]:
    """Return editable system settings as key-value strings."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT key, value
            FROM settings
            ORDER BY key
            """
        ).fetchall()

    return {row["key"]: row["value"] for row in rows}


def get_recent_decision_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent decision logs, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            SELECT_RECENT_DECISION_LOGS,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def count_decisions_by_alert_level() -> list[dict[str, Any]]:
    """Return decision counts grouped by alert level."""
    with get_db_connection() as connection:
        rows = connection.execute(COUNT_DECISIONS_BY_ALERT_LEVEL).fetchall()

    return [_row_to_dict(row) for row in rows]


def count_decisions_by_type() -> list[dict[str, Any]]:
    """Return decision counts grouped by decision type."""
    with get_db_connection() as connection:
        rows = connection.execute(COUNT_DECISIONS_BY_TYPE).fetchall()

    return [_row_to_dict(row) for row in rows]


def get_recent_session_analytics(limit: int = 20) -> list[dict[str, Any]]:
    """Return recently saved session analytics summaries, newest first."""
    with get_db_connection() as connection:
        rows = connection.execute(
            SELECT_RECENT_SESSION_ANALYTICS,
            (_safe_limit(limit),),
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def _safe_limit(limit: int) -> int:
    return max(1, int(limit))


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
