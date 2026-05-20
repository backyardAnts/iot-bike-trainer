"""Read helpers for future dashboard and reporting phases."""

from __future__ import annotations

from typing import Any

from database_layer.db_connection import get_db_connection


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


def _safe_limit(limit: int) -> int:
    return max(1, int(limit))


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
