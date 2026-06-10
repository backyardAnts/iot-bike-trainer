"""Write MQTT backend data into SQLite.

This module is the write side of the local database layer. It accepts validated
payloads from the backend and keeps athlete/session links consistent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from typing import Any

from common.time_utils import get_current_timestamp
from config_layer import thresholds
from database_layer.db_connection import get_db_connection
from database_layer.migrations import ensure_legacy_athlete
from database_layer.queries import INSERT_DECISION_LOG, INSERT_SESSION_ANALYTICS


PASSWORD_HASH_ITERATIONS = 120_000


def create_athlete_account(
    name: str,
    email: str | None = None,
    password: str | None = None,
    password_hash: str | None = None,
    age: int | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    gender: str | None = None,
    fitness_level: str | None = None,
    max_heart_rate: int | None = None,
    training_goal: str | None = None,
) -> dict[str, Any]:
    """Create or update one athlete account and return the stored row."""
    # Accept either a raw password or a precomputed hash for tests/imports.
    athlete_data = {
        "name": name,
        "email": email,
        "password_hash": password_hash or (
            hash_password(password) if password else None
        ),
        "age": age,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "gender": gender,
        "fitness_level": fitness_level,
        "max_heart_rate": max_heart_rate,
        "training_goal": training_goal,
    }
    with get_db_connection() as connection:
        athlete_id = _create_or_update_athlete(connection, athlete_data)
        athlete = _get_athlete_by_id(connection, athlete_id)
        if athlete is None:
            raise RuntimeError("Created athlete could not be loaded.")
        return athlete


def get_athlete_by_id(athlete_id: int | str) -> dict[str, Any] | None:
    """Return one athlete account by database id."""
    with get_db_connection() as connection:
        return _get_athlete_by_id(connection, athlete_id)


def get_athlete_by_email(email: str) -> dict[str, Any] | None:
    """Return one athlete account by normalized email."""
    normalized_email = _normalize_email(email)
    if normalized_email is None:
        return None
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM athletes
            WHERE lower(email) = lower(?)
            LIMIT 1
            """,
            (normalized_email,),
        ).fetchone()
    return dict(row) if row is not None else None


def update_athlete_profile(
    athlete_id: int | str,
    **profile_updates: Any,
) -> dict[str, Any] | None:
    """Update supported athlete profile fields and return the updated account."""
    # Ignore unknown fields so callers can pass larger profile payloads safely.
    allowed_fields = {
        "name",
        "email",
        "password_hash",
        "age",
        "height_cm",
        "weight_kg",
        "gender",
        "fitness_level",
        "max_heart_rate",
        "training_goal",
    }
    updates = {
        key: value
        for key, value in profile_updates.items()
        if key in allowed_fields
    }
    if "password" in profile_updates and "password_hash" not in updates:
        updates["password_hash"] = hash_password(str(profile_updates["password"]))
    if not updates:
        return get_athlete_by_id(athlete_id)

    if "email" in updates:
        updates["email"] = _normalize_email(updates["email"])
    if "name" in updates:
        updates["name"] = _non_empty_text(updates["name"]) or "Athlete"

    assignments = ", ".join(f"{field} = ?" for field in updates)
    values = list(updates.values())
    values.extend([get_current_timestamp(), int(athlete_id)])

    with get_db_connection() as connection:
        connection.execute(
            f"""
            UPDATE athletes
            SET {assignments},
                updated_at = ?
            WHERE id = ?
            """,
            values,
        )
        return _get_athlete_by_id(connection, athlete_id)


def get_or_create_legacy_athlete() -> dict[str, Any]:
    """Return the default athlete used by existing pre-account data."""
    with get_db_connection() as connection:
        athlete_id = ensure_legacy_athlete(connection)
        athlete = _get_athlete_by_id(connection, athlete_id)
        if athlete is None:
            raise RuntimeError("Legacy athlete could not be loaded.")
        return athlete


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 for lightweight login support."""
    # The salt is stored with the hash so each password has a unique digest.
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_HASH_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Return True when a plain password matches a stored PBKDF2 hash."""
    parts = str(stored_hash).split("$")
    if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
        return False
    try:
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_digest = bytes.fromhex(parts[3])
    except ValueError:
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt,
        iterations,
    )
    # compare_digest avoids leaking timing clues for wrong passwords.
    return hmac.compare_digest(actual_digest, expected_digest)


def get_athlete_for_session(session_id: str, device_id: str | None = None) -> dict[str, Any] | None:
    """Return the athlete linked to a session, falling back to legacy."""
    with get_db_connection() as connection:
        athlete_id = _resolve_athlete_id_for_session(
            connection,
            session_id,
            device_id=device_id,
            create_legacy=True,
        )
        return _get_athlete_by_id(connection, athlete_id)


def get_athlete_session_history(
    athlete_id: int | str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent sessions for one athlete."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sessions
            WHERE athlete_id = ?
            ORDER BY COALESCE(end_time, start_time) DESC, id DESC
            LIMIT ?
            """,
            (int(athlete_id), _safe_limit(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def get_athlete_analytics(
    athlete_id: int | str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent saved analytics rows for one athlete."""
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM session_analytics
            WHERE athlete_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(athlete_id), _safe_limit(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def start_session_for_athlete(
    athlete_id: int | str,
    session_id: str,
    device_id: str,
    start_time: str,
) -> None:
    """Create or update an active session for a specific athlete."""
    start_session(
        session_id,
        device_id,
        start_time,
        athlete_id=int(athlete_id),
    )


def end_session_for_athlete(
    athlete_id: int | str,
    session_id: str,
    end_time: str,
) -> None:
    """Stop an active session for a specific athlete."""
    stop_session(session_id, end_time, athlete_id=int(athlete_id))


def save_sensor_reading(
    message: dict[str, Any],
    athlete_id: int | None = None,
) -> None:
    """Save one validated sensor reading using the current rider feedback schema."""
    received_at = get_current_timestamp()

    with get_db_connection() as connection:
        # Every reading should be linked to an athlete, even legacy/demo data.
        resolved_athlete_id = _resolve_athlete_id_for_session(
            connection,
            str(message["session_id"]),
            device_id=str(message.get("device_id", "")),
            athlete_id=athlete_id or _optional_int(message.get("athlete_id")),
            create_legacy=True,
        )
        connection.execute(
            """
            INSERT INTO sensor_readings (
                athlete_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_athlete_id,
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
    parsed_payload = _parse_json_object(str(payload))
    with get_db_connection() as connection:
        # Raw payload is stored either way; parsed fields are used when present.
        session_id = _optional_text(
            parsed_payload.get("session_id") if parsed_payload else None
        )
        device_id = _optional_text(
            parsed_payload.get("device_id") if parsed_payload else None
        )
        athlete_id = None
        if parsed_payload is not None:
            athlete_id = _athlete_id_from_payload(connection, parsed_payload)
            if athlete_id is None and session_id:
                athlete_id = _resolve_athlete_id_for_session(
                    connection,
                    session_id,
                    device_id=device_id,
                    create_legacy=False,
                )
        connection.execute(
            """
            INSERT INTO mqtt_status_messages (
                athlete_id,
                device_id,
                session_id,
                topic,
                payload,
                received_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (athlete_id, device_id, session_id, topic, payload, get_current_timestamp()),
        )


def save_command(payload: dict[str, Any] | str) -> None:
    """Save a raw command message and its command name when available."""
    command = None

    if isinstance(payload, dict):
        # Store JSON compactly so command history is readable and searchable.
        command = _extract_command(payload)
        payload_text = json.dumps(payload, separators=(",", ":"))
        command_payload = payload
    else:
        payload_text = str(payload)
        parsed_payload = _parse_json_object(payload_text)
        if parsed_payload is not None:
            command = _extract_command(parsed_payload)
        command_payload = parsed_payload

    with get_db_connection() as connection:
        session_id = _optional_text(
            command_payload.get("session_id") if command_payload else None
        )
        device_id = _optional_text(
            command_payload.get("device_id") if command_payload else None
        )
        athlete_id = None
        if command_payload is not None:
            athlete_id = _athlete_id_from_payload(connection, command_payload)
            if athlete_id is None and session_id:
                athlete_id = _resolve_athlete_id_for_session(
                    connection,
                    session_id,
                    device_id=device_id,
                    create_legacy=False,
                )
        connection.execute(
            """
            INSERT INTO commands (
                athlete_id,
                device_id,
                session_id,
                command,
                payload,
                received_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                athlete_id,
                device_id,
                session_id,
                command,
                payload_text,
                get_current_timestamp(),
            ),
        )


def save_session_metadata(
    session_id: str,
    device_id: str = "",
    workout_type: str = "",
    mode: str = "",
    athlete: dict[str, Any] | None = None,
    athlete_id: int | None = None,
) -> None:
    """Store dashboard-provided athlete/session metadata for a workout session."""
    session_id = str(session_id).strip()
    if not session_id:
        return

    # Keep the full athlete object while also splitting useful fields into columns.
    athlete_data = dict(athlete) if isinstance(athlete, dict) else {}
    now = get_current_timestamp()
    athlete_json = json.dumps(athlete_data, separators=(",", ":"), sort_keys=True)

    with get_db_connection() as connection:
        resolved_athlete_id = _athlete_id_from_payload(
            connection,
            {"athlete_id": athlete_id, "athlete": athlete_data},
        )
        if resolved_athlete_id is None:
            resolved_athlete_id = _resolve_athlete_id_for_session(
                connection,
                session_id,
                device_id=device_id,
                athlete=athlete_data,
                create_legacy=True,
            )
        _link_session_to_athlete(
            connection,
            session_id,
            device_id,
            resolved_athlete_id,
        )
        # Upsert lets repeated START/status messages refresh the same session row.
        connection.execute(
            """
            INSERT INTO session_metadata (
                athlete_id,
                session_id,
                device_id,
                workout_type,
                mode,
                athlete_name,
                athlete_age,
                athlete_weight_kg,
                athlete_height_cm,
                athlete_email,
                athlete_gender,
                athlete_fitness_level,
                athlete_max_heart_rate,
                athlete_training_goal,
                athlete_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                athlete_id = excluded.athlete_id,
                device_id = excluded.device_id,
                workout_type = excluded.workout_type,
                mode = excluded.mode,
                athlete_name = excluded.athlete_name,
                athlete_age = excluded.athlete_age,
                athlete_weight_kg = excluded.athlete_weight_kg,
                athlete_height_cm = excluded.athlete_height_cm,
                athlete_email = excluded.athlete_email,
                athlete_gender = excluded.athlete_gender,
                athlete_fitness_level = excluded.athlete_fitness_level,
                athlete_max_heart_rate = excluded.athlete_max_heart_rate,
                athlete_training_goal = excluded.athlete_training_goal,
                athlete_json = excluded.athlete_json,
                updated_at = excluded.updated_at
            """,
            (
                resolved_athlete_id,
                session_id,
                str(device_id),
                str(workout_type),
                str(mode),
                _optional_text(athlete_data.get("name")),
                _optional_int(athlete_data.get("age")),
                _optional_float(athlete_data.get("weight_kg")),
                _optional_float(athlete_data.get("height_cm")),
                _optional_text(athlete_data.get("email")),
                _optional_text(athlete_data.get("gender")),
                _optional_text(athlete_data.get("fitness_level")),
                _optional_int(athlete_data.get("max_heart_rate")),
                _optional_text(athlete_data.get("training_goal")),
                athlete_json,
                now,
            ),
        )


def save_decision_log(
    sensor_message: dict[str, Any],
    decision: Any,
    source_topic: str | None = None,
    athlete_id: int | None = None,
) -> None:
    """Save one backend decision made for a sensor message."""
    decision_data = _decision_to_dict(decision)

    with get_db_connection() as connection:
        # Resolve the same athlete as the sensor reading so reports line up.
        resolved_athlete_id = _resolve_athlete_id_for_session(
            connection,
            str(sensor_message.get("session_id", "")),
            device_id=str(sensor_message.get("device_id", "")),
            athlete_id=athlete_id or _optional_int(sensor_message.get("athlete_id")),
            create_legacy=True,
        )
        connection.execute(
            INSERT_DECISION_LOG,
            (
                resolved_athlete_id,
                str(sensor_message["device_id"]),
                sensor_message.get("session_id"),
                str(sensor_message["timestamp"]),
                decision_data.get("workout_type", sensor_message.get("workout_type")),
                str(decision_data["decision_type"]),
                str(decision_data["alert_level"]),
                decision_data.get("alert_side"),
                int(bool(decision_data.get("display_active", False))),
                decision_data.get("display_message"),
                decision_data.get("speaker_message"),
                decision_data.get("recommended_action"),
                source_topic,
            ),
        )


def save_session_analytics(analytics: dict[str, Any]) -> None:
    """Save one calculated session analytics summary."""
    with get_db_connection() as connection:
        # Saved summaries are tied back to the athlete for dashboard filtering.
        athlete_id = _resolve_athlete_id_for_session(
            connection,
            str(analytics["session_id"]),
            athlete_id=_optional_int(analytics.get("athlete_id")),
            create_legacy=True,
        )
        connection.execute(
            INSERT_SESSION_ANALYTICS,
            (
                athlete_id,
                str(analytics["session_id"]),
                get_current_timestamp(),
                float(analytics["average_speed_kmh"]),
                float(analytics["average_cadence_rpm"]),
                float(analytics["average_heart_rate_bpm"]),
                int(analytics["max_heart_rate_bpm"]),
                int(analytics["min_heart_rate_bpm"]),
                int(analytics["total_readings"]),
                int(analytics["session_duration_seconds"]),
                int(analytics["time_in_zone_easy"]),
                int(analytics["time_in_zone_moderate"]),
                int(analytics["time_in_zone_hard"]),
                int(analytics["time_in_zone_peak"]),
                str(analytics["improvement_vs_previous_session"]),
            ),
        )


def get_session_report_email_record(session_id: str) -> dict[str, Any] | None:
    """Return the email-report tracking row for a session, if one exists."""
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM session_report_emails
            WHERE session_id = ?
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    return dict(row) if row is not None else None


def reserve_session_report_email(
    session_id: str,
    workout_type: str,
    subject: str,
    body: str,
    athlete_id: int | None = None,
) -> bool:
    """Reserve one session report email so duplicate stopped events cannot resend."""
    now = get_current_timestamp()
    try:
        with get_db_connection() as connection:
            resolved_athlete_id = _resolve_athlete_id_for_session(
                connection,
                session_id,
                athlete_id=athlete_id,
                create_legacy=True,
            )
            connection.execute(
                """
                INSERT INTO session_report_emails (
                    athlete_id,
                    session_id,
                    workout_type,
                    email_status,
                    email_to,
                    report_subject,
                    report_body,
                    error_message,
                    generated_at,
                    sent_at
                )
                VALUES (?, ?, ?, 'pending', NULL, ?, ?, NULL, ?, NULL)
                """,
                (resolved_athlete_id, session_id, workout_type, subject, body, now),
            )
    except sqlite3.IntegrityError:
        # session_id is unique here; an integrity error means it was reserved.
        return False

    return True


def update_session_report_email_result(
    session_id: str,
    email_status: str,
    email_to: str,
    error_message: str = "",
) -> None:
    """Store the final send/skip/failure result for a reserved report email."""
    sent_at = get_current_timestamp() if email_status == "sent" else None
    with get_db_connection() as connection:
        connection.execute(
            """
            UPDATE session_report_emails
            SET email_status = ?,
                email_to = ?,
                error_message = ?,
                sent_at = ?
            WHERE session_id = ?
            """,
            (email_status, email_to, error_message, sent_at, session_id),
        )


def start_session(
    session_id: str,
    device_id: str,
    start_time: str,
    athlete_id: int | None = None,
    athlete: dict[str, Any] | None = None,
) -> None:
    """Create an active session row unless one is already active."""
    with get_db_connection() as connection:
        resolved_athlete_id = _resolve_athlete_id_for_session(
            connection,
            session_id,
            device_id=device_id,
            athlete_id=athlete_id,
            athlete=athlete,
            create_legacy=True,
        )
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
            # Restarting an active session refreshes the row instead of duplicating it.
            connection.execute(
                """
                UPDATE sessions
                SET athlete_id = ?, start_time = ?, end_time = NULL, status = 'active'
                WHERE id = ?
                """,
                (resolved_athlete_id, start_time, active_session["id"]),
            )
            return

        connection.execute(
            """
            INSERT INTO sessions (
                athlete_id,
                session_id,
                device_id,
                start_time,
                end_time,
                status
            )
            VALUES (?, ?, ?, ?, NULL, 'active')
            """,
            (resolved_athlete_id, session_id, device_id, start_time),
        )


def stop_session(
    session_id: str,
    end_time: str,
    athlete_id: int | None = None,
) -> None:
    """Mark active rows for a session as stopped."""
    with get_db_connection() as connection:
        resolved_athlete_id = _resolve_athlete_id_for_session(
            connection,
            session_id,
            athlete_id=athlete_id,
            create_legacy=False,
        )
        if resolved_athlete_id is not None:
            connection.execute(
                """
                UPDATE sessions
                SET athlete_id = ?, end_time = ?, status = 'stopped'
                WHERE session_id = ? AND status = 'active'
                """,
                (resolved_athlete_id, end_time, session_id),
            )
            return

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
    # These become editable settings for later dashboard work.
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
        athlete_id = _resolve_athlete_id_for_session(
            connection,
            str(alert.get("session_id", "")),
            device_id=_optional_text(alert.get("device_id")),
            athlete_id=_optional_int(alert.get("athlete_id")),
            create_legacy=False,
        )
        connection.execute(
            """
            INSERT INTO alerts (
                athlete_id,
                timestamp,
                device_id,
                session_id,
                alert_type,
                alert_level,
                message,
                action,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                athlete_id,
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
    """Return the normalized command name from a payload."""
    command = payload.get("command")
    return str(command).strip().upper() if command else None


def _decision_to_dict(decision: Any) -> dict[str, Any]:
    """Accept either a decision dictionary or an object with to_dict()."""
    if isinstance(decision, dict):
        return decision

    if hasattr(decision, "to_dict"):
        decision_data = decision.to_dict()
        if isinstance(decision_data, dict):
            return decision_data

    raise TypeError("decision must be a dictionary or expose to_dict()")


def _parse_json_object(payload: str) -> dict[str, Any] | None:
    """Parse JSON text and accept only objects."""
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _optional_text(value: Any) -> str | None:
    """Return stripped text, or None for blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    """Parse an integer, returning None for bad values and booleans."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    """Parse a float, returning None for bad values and booleans."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_athlete_id_for_session(
    connection: sqlite3.Connection,
    session_id: str,
    device_id: str | None = None,
    athlete_id: int | None = None,
    athlete: dict[str, Any] | None = None,
    create_legacy: bool = False,
) -> int | None:
    """Resolve the best athlete ID for a session-related write."""
    explicit_athlete_id = _valid_athlete_id(connection, athlete_id)
    if explicit_athlete_id is not None:
        return explicit_athlete_id

    athlete_data = dict(athlete) if isinstance(athlete, dict) else {}
    payload_athlete_id = _athlete_id_from_profile(connection, athlete_data)
    if payload_athlete_id is not None:
        return payload_athlete_id

    session_athlete_id = _find_athlete_id_for_session(
        connection,
        session_id,
        device_id=device_id,
    )
    if session_athlete_id is not None:
        return session_athlete_id

    if _has_athlete_profile_data(athlete_data):
        return _create_or_update_athlete(connection, athlete_data)

    if create_legacy:
        # Legacy athlete keeps old/no-profile data queryable by athlete filters.
        return ensure_legacy_athlete(connection)

    return None


def _athlete_id_from_payload(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
) -> int | None:
    """Resolve athlete ID from command/status payload fields."""
    athlete_id = _valid_athlete_id(
        connection,
        _optional_int(payload.get("athlete_id") or payload.get("user_id")),
    )
    if athlete_id is not None:
        return athlete_id

    athlete = payload.get("athlete") or payload.get("user")
    if isinstance(athlete, dict):
        return _resolve_athlete_id_for_session(
            connection,
            str(payload.get("session_id", "")),
            device_id=_optional_text(payload.get("device_id")),
            athlete=athlete,
            create_legacy=False,
        )

    return None


def _athlete_id_from_profile(
    connection: sqlite3.Connection,
    athlete: dict[str, Any],
) -> int | None:
    """Resolve an athlete ID from an embedded athlete profile."""
    athlete_id = _valid_athlete_id(
        connection,
        _optional_int(
            athlete.get("athlete_id")
            or athlete.get("user_id")
            or athlete.get("id")
        ),
    )
    if athlete_id is not None:
        return athlete_id

    email = _normalize_email(athlete.get("email"))
    if email is not None:
        profile = dict(athlete)
        profile["email"] = email
        return _create_or_update_athlete(connection, profile)

    return None


def _create_or_update_athlete(
    connection: sqlite3.Connection,
    athlete: dict[str, Any],
) -> int:
    """Create or update an athlete row and return its ID."""
    athlete_id = _valid_athlete_id(
        connection,
        _optional_int(
            athlete.get("athlete_id")
            or athlete.get("user_id")
            or athlete.get("id")
        ),
    )
    if athlete_id is not None:
        _update_athlete_row(connection, athlete_id, athlete)
        return athlete_id

    email = _normalize_email(athlete.get("email"))
    name = _non_empty_text(athlete.get("name")) or "Athlete"
    now = get_current_timestamp()
    if email is None:
        values = _athlete_values(name, None, athlete, now)
        cursor = connection.execute(
            """
            INSERT INTO athletes (
                name,
                email,
                password_hash,
                age,
                height_cm,
                weight_kg,
                gender,
                fitness_level,
                max_heart_rate,
                training_goal,
                created_at,
                updated_at
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values[:1] + values[2:],
        )
        return int(cursor.lastrowid)

    connection.execute(
        """
        INSERT INTO athletes (
            name,
            email,
            password_hash,
            age,
            height_cm,
            weight_kg,
            gender,
            fitness_level,
            max_heart_rate,
            training_goal,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = COALESCE(excluded.name, athletes.name),
            password_hash = COALESCE(excluded.password_hash, athletes.password_hash),
            age = COALESCE(excluded.age, athletes.age),
            height_cm = COALESCE(excluded.height_cm, athletes.height_cm),
            weight_kg = COALESCE(excluded.weight_kg, athletes.weight_kg),
            gender = COALESCE(excluded.gender, athletes.gender),
            fitness_level = COALESCE(excluded.fitness_level, athletes.fitness_level),
            max_heart_rate = COALESCE(excluded.max_heart_rate, athletes.max_heart_rate),
            training_goal = COALESCE(excluded.training_goal, athletes.training_goal),
            updated_at = excluded.updated_at
        """,
        _athlete_values(name, email, athlete, now),
    )
    row = connection.execute(
        """
        SELECT id
        FROM athletes
        WHERE lower(email) = lower(?)
        LIMIT 1
        """,
        (email,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Athlete could not be created.")
    return int(row["id"])


def _update_athlete_row(
    connection: sqlite3.Connection,
    athlete_id: int,
    athlete: dict[str, Any],
) -> None:
    """Update an existing athlete row with any supplied profile fields."""
    updates = {
        "name": _non_empty_text(athlete.get("name")),
        "email": _normalize_email(athlete.get("email")),
        "password_hash": _optional_text(athlete.get("password_hash")),
        "age": _optional_int(athlete.get("age")),
        "height_cm": _optional_float(athlete.get("height_cm")),
        "weight_kg": _optional_float(athlete.get("weight_kg")),
        "gender": _optional_text(athlete.get("gender")),
        "fitness_level": _optional_text(athlete.get("fitness_level")),
        "max_heart_rate": _optional_int(athlete.get("max_heart_rate")),
        "training_goal": _optional_text(athlete.get("training_goal")),
    }
    updates = {key: value for key, value in updates.items() if value is not None}
    if not updates:
        return
    assignments = ", ".join(f"{field} = ?" for field in updates)
    values = list(updates.values())
    values.extend([get_current_timestamp(), athlete_id])
    connection.execute(
        f"""
        UPDATE athletes
        SET {assignments},
            updated_at = ?
        WHERE id = ?
        """,
        values,
    )


def _athlete_values(
    name: str,
    email: str | None,
    athlete: dict[str, Any],
    now: str,
) -> tuple[Any, ...]:
    """Build the ordered athlete values used by INSERT statements."""
    return (
        name,
        email,
        _optional_text(athlete.get("password_hash")),
        _optional_int(athlete.get("age")),
        _optional_float(athlete.get("height_cm")),
        _optional_float(athlete.get("weight_kg")),
        _optional_text(athlete.get("gender")),
        _optional_text(athlete.get("fitness_level")),
        _optional_int(athlete.get("max_heart_rate")),
        _optional_text(athlete.get("training_goal")),
        now,
        now,
    )


def _find_athlete_id_for_session(
    connection: sqlite3.Connection,
    session_id: str,
    device_id: str | None = None,
) -> int | None:
    """Find an athlete already linked to this session in known tables."""
    session_id = str(session_id).strip()
    if not session_id:
        return None

    session_filters = ["session_id = ?", "athlete_id IS NOT NULL"]
    parameters = [session_id]
    if device_id:
        session_filters.append("device_id = ?")
        parameters.append(str(device_id))
    row = connection.execute(
        f"""
        SELECT athlete_id
        FROM sessions
        WHERE {' AND '.join(session_filters)}
        ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, id DESC
        LIMIT 1
        """,
        parameters,
    ).fetchone()
    if row is not None:
        return int(row["athlete_id"])

    for table in ("session_metadata", "sensor_readings", "decision_logs"):
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


def _link_session_to_athlete(
    connection: sqlite3.Connection,
    session_id: str,
    device_id: str,
    athlete_id: int | None,
) -> None:
    """Backfill athlete_id into rows that belong to a session."""
    if athlete_id is None:
        return
    connection.execute(
        """
        UPDATE sessions
        SET athlete_id = ?
        WHERE session_id = ?
          AND (? = '' OR device_id = ?)
        """,
        (athlete_id, session_id, str(device_id), str(device_id)),
    )
    for table in ("sensor_readings", "decision_logs", "session_analytics"):
        connection.execute(
            f"""
            UPDATE {table}
            SET athlete_id = ?
            WHERE session_id = ?
              AND athlete_id IS NULL
            """,
            (athlete_id, session_id),
        )


def _valid_athlete_id(
    connection: sqlite3.Connection,
    athlete_id: int | None,
) -> int | None:
    """Return athlete_id only when it exists in the athletes table."""
    if athlete_id is None:
        return None
    row = connection.execute(
        """
        SELECT id
        FROM athletes
        WHERE id = ?
        LIMIT 1
        """,
        (int(athlete_id),),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _get_athlete_by_id(
    connection: sqlite3.Connection,
    athlete_id: int | str,
) -> dict[str, Any] | None:
    """Load an athlete row by ID, guarding against bad input."""
    try:
        athlete_id_int = int(athlete_id)
    except (TypeError, ValueError):
        return None
    row = connection.execute(
        """
        SELECT *
        FROM athletes
        WHERE id = ?
        LIMIT 1
        """,
        (athlete_id_int,),
    ).fetchone()
    return dict(row) if row is not None else None


def _has_athlete_profile_data(athlete: dict[str, Any]) -> bool:
    """Return True when a payload has enough data to create an athlete row."""
    for key in (
        "name",
        "email",
        "age",
        "height_cm",
        "weight_kg",
        "gender",
        "fitness_level",
        "max_heart_rate",
        "training_goal",
    ):
        if _optional_text(athlete.get(key)) is not None:
            return True
    return False


def _normalize_email(value: Any) -> str | None:
    """Normalize email text for comparisons and unique constraints."""
    text = _optional_text(value)
    return text.lower() if text is not None else None


def _non_empty_text(value: Any) -> str | None:
    """Alias used where text-specific intent reads better than optional_text."""
    return _optional_text(value)


def _safe_limit(limit: int) -> int:
    """Keep query limits positive."""
    return max(1, int(limit))
