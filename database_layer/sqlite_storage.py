"""Write MQTT backend data into SQLite."""

from __future__ import annotations

import json
from typing import Any

from common.time_utils import get_current_timestamp
from config_layer import thresholds
from database_layer.db_connection import get_db_connection


def save_sensor_reading(message: dict[str, Any]) -> None:
    """Save one validated sensor reading using the current rider feedback schema."""
    received_at = get_current_timestamp()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO sensor_readings (
                device_id,
                session_id,
                timestamp,
                speed_kmh,
                cadence_rpm,
                heart_rate_bpm,
                temperature_c,
                left_distance_m,
                right_distance_m,
                display_active,
                display_message,
                speaker_message,
                alert_level,
                alert_side,
                received_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message["device_id"],
                message["session_id"],
                message["timestamp"],
                float(message["speed_kmh"]),
                int(message["cadence_rpm"]),
                int(message["heart_rate_bpm"]),
                float(message["temperature_c"]),
                float(message["left_distance_m"]),
                float(message["right_distance_m"]),
                int(bool(message["display_active"])),
                message["display_message"],
                message["speaker_message"],
                message["alert_level"],
                message["alert_side"],
                received_at,
            ),
        )


def save_status_message(topic: str, payload: str) -> None:
    """Save a raw MQTT status message."""
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO mqtt_status_messages (topic, payload, received_at)
            VALUES (?, ?, ?)
            """,
            (topic, payload, get_current_timestamp()),
        )


def save_command(payload: dict[str, Any] | str) -> None:
    """Save a raw command message and its command name when available."""
    command = None

    if isinstance(payload, dict):
        command = _extract_command(payload)
        payload_text = json.dumps(payload, separators=(",", ":"))
    else:
        payload_text = str(payload)
        parsed_payload = _parse_json_object(payload_text)
        if parsed_payload is not None:
            command = _extract_command(parsed_payload)

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO commands (command, payload, received_at)
            VALUES (?, ?, ?)
            """,
            (command, payload_text, get_current_timestamp()),
        )


def start_session(session_id: str, device_id: str, start_time: str) -> None:
    """Create an active session row unless one is already active."""
    with get_db_connection() as connection:
        active_session = connection.execute(
            """
            SELECT id
            FROM sessions
            WHERE session_id = ? AND device_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, device_id),
        ).fetchone()

        if active_session is not None:
            connection.execute(
                """
                UPDATE sessions
                SET start_time = ?, end_time = NULL, status = 'active'
                WHERE id = ?
                """,
                (start_time, active_session["id"]),
            )
            return

        connection.execute(
            """
            INSERT INTO sessions (
                session_id,
                device_id,
                start_time,
                end_time,
                status
            )
            VALUES (?, ?, ?, NULL, 'active')
            """,
            (session_id, device_id, start_time),
        )


def stop_session(session_id: str, end_time: str) -> None:
    """Mark active rows for a session as stopped."""
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE sessions
            SET end_time = ?, status = 'stopped'
            WHERE session_id = ? AND status = 'active'
            """,
            (end_time, session_id),
        )


def initialize_default_settings() -> None:
    """Insert default threshold settings if they do not already exist."""
    now = get_current_timestamp()
    defaults = {
        "danger_distance_m": thresholds.DANGER_DISTANCE_M,
        "high_heart_rate_bpm": thresholds.HIGH_HEART_RATE_BPM,
        "low_cadence_rpm": thresholds.LOW_CADENCE_RPM,
        "high_cadence_rpm": thresholds.HIGH_CADENCE_RPM,
        "high_temperature_c": thresholds.HIGH_TEMPERATURE_C,
    }

    with get_db_connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            [(key, str(value), now) for key, value in defaults.items()],
        )


def save_alert(alert: dict[str, Any]) -> None:
    """Save a future AI alert. Phase 6 only prepares this table."""
    now = get_current_timestamp()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO alerts (
                timestamp,
                device_id,
                session_id,
                alert_type,
                alert_level,
                message,
                action,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(alert.get("timestamp", now)),
                alert.get("device_id"),
                alert.get("session_id"),
                str(alert["alert_type"]),
                str(alert["alert_level"]),
                str(alert["message"]),
                alert.get("action"),
                now,
            ),
        )


def _extract_command(payload: dict[str, Any]) -> str | None:
    command = payload.get("command")
    return str(command).strip().upper() if command else None


def _parse_json_object(payload: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None
