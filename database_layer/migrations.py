"""Safe SQLite schema upgrade helpers.

These migrations add account/session fields to existing local databases without
deleting sensor readings that were already captured.
"""

from __future__ import annotations

import json
import sqlite3

from common.time_utils import get_current_timestamp


LEGACY_ATHLETE_NAME = "Legacy Athlete"
LEGACY_ATHLETE_EMAIL = "legacy-athlete@local"


def run_schema_migrations(connection: sqlite3.Connection) -> None:
    """Upgrade existing SQLite databases without deleting old data."""
    # Order matters: create tables first, then columns/indexes, then backfill.
    _create_athletes_table(connection)
    _add_missing_columns(connection)
    _create_indexes(connection)
    legacy_athlete_id = ensure_legacy_athlete(connection)
    _backfill_legacy_rows(connection, legacy_athlete_id)


def ensure_legacy_athlete(connection: sqlite3.Connection) -> int:
    """Return the default athlete used for pre-account legacy data."""
    # Old data did not know about athlete accounts, so it is linked here.
    now = get_current_timestamp()
    connection.execute(
        """
        INSERT OR IGNORE INTO athletes (
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
        VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, 'legacy', NULL, NULL, ?, ?)
        """,
        (LEGACY_ATHLETE_NAME, LEGACY_ATHLETE_EMAIL, now, now),
    )
    row = connection.execute(
        """
        SELECT id
        FROM athletes
        WHERE email = ?
        LIMIT 1
        """,
        (LEGACY_ATHLETE_EMAIL,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Could not create or load legacy athlete.")
    return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])


def _create_athletes_table(connection: sqlite3.Connection) -> None:
    """Create the athletes table used by newer account-aware features."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS athletes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT,
            age INTEGER,
            height_cm REAL,
            weight_kg REAL,
            gender TEXT,
            fitness_level TEXT,
            max_heart_rate INTEGER,
            training_goal TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Add account/session columns that may not exist in older databases."""
    column_specs = {
        "sensor_readings": {
            "athlete_id": "INTEGER",
        },
        "mqtt_status_messages": {
            "athlete_id": "INTEGER",
            "device_id": "TEXT",
            "session_id": "TEXT",
        },
        "commands": {
            "athlete_id": "INTEGER",
            "device_id": "TEXT",
            "session_id": "TEXT",
        },
        "sessions": {
            "athlete_id": "INTEGER",
        },
        "session_metadata": {
            "athlete_id": "INTEGER",
            "athlete_gender": "TEXT",
            "athlete_fitness_level": "TEXT",
            "athlete_max_heart_rate": "INTEGER",
            "athlete_training_goal": "TEXT",
        },
        "alerts": {
            "athlete_id": "INTEGER",
        },
        "decision_logs": {
            "athlete_id": "INTEGER",
        },
        "session_analytics": {
            "athlete_id": "INTEGER",
        },
        "session_report_emails": {
            "athlete_id": "INTEGER",
        },
    }
    for table, specs in column_specs.items():
        existing_columns = _table_columns(connection, table)
        if not existing_columns:
            continue
        for column_name, column_type in specs.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"
            )


def _create_indexes(connection: sqlite3.Connection) -> None:
    """Create indexes used by dashboard/reporting queries."""
    index_statements = (
        "CREATE INDEX IF NOT EXISTS idx_athletes_email ON athletes(email)",
        "CREATE INDEX IF NOT EXISTS idx_sensor_readings_athlete ON sensor_readings(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_commands_session ON commands(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_commands_athlete ON commands(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_status_session ON mqtt_status_messages(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_status_athlete ON mqtt_status_messages(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_sessions_athlete ON sessions(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_session_metadata_athlete ON session_metadata(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_decision_logs_athlete ON decision_logs(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_session_analytics_athlete ON session_analytics(athlete_id)",
        "CREATE INDEX IF NOT EXISTS idx_session_report_emails_athlete ON session_report_emails(athlete_id)",
    )
    for statement in index_statements:
        connection.execute(statement)


def _backfill_legacy_rows(
    connection: sqlite3.Connection,
    legacy_athlete_id: int,
) -> None:
    """Attach older rows to the legacy athlete where no better data exists."""
    _backfill_session_metadata_from_athlete_email(connection, legacy_athlete_id)

    connection.execute(
        """
        UPDATE sessions
        SET athlete_id = ?
        WHERE athlete_id IS NULL
        """,
        (legacy_athlete_id,),
    )
    connection.execute(
        """
        UPDATE session_metadata
        SET athlete_id = ?
        WHERE athlete_id IS NULL
        """,
        (legacy_athlete_id,),
    )
    for table in (
        "sensor_readings",
        "decision_logs",
        "session_analytics",
        "session_report_emails",
    ):
        _backfill_from_sessions(connection, table, legacy_athlete_id)
    _backfill_message_table_payloads(connection, "commands", legacy_athlete_id)
    _backfill_message_table_payloads(
        connection,
        "mqtt_status_messages",
        legacy_athlete_id,
    )


def _backfill_session_metadata_from_athlete_email(
    connection: sqlite3.Connection,
    legacy_athlete_id: int,
) -> None:
    """Create athlete rows from old session_metadata email fields."""
    if not _table_columns(connection, "session_metadata"):
        return

    rows = connection.execute(
        """
        SELECT *
        FROM session_metadata
        WHERE athlete_id IS NULL
          AND athlete_email IS NOT NULL
          AND athlete_email != ''
        """
    ).fetchall()
    for row in rows:
        athlete_id = _create_or_update_athlete_from_metadata(connection, row)
        connection.execute(
            """
            UPDATE session_metadata
            SET athlete_id = ?
            WHERE id = ?
            """,
            (athlete_id or legacy_athlete_id, row["id"]),
        )
        connection.execute(
            """
            UPDATE sessions
            SET athlete_id = ?
            WHERE session_id = ?
            """,
            (athlete_id or legacy_athlete_id, row["session_id"]),
        )


def _create_or_update_athlete_from_metadata(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> int | None:
    """Create or update an athlete using one session_metadata row."""
    email = str(row["athlete_email"] or "").strip().lower()
    if not email:
        return None

    now = get_current_timestamp()
    name = str(row["athlete_name"] or "").strip() or "Athlete"
    connection.execute(
        """
        INSERT INTO athletes (
            name,
            email,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name = excluded.name,
            age = excluded.age,
            height_cm = excluded.height_cm,
            weight_kg = excluded.weight_kg,
            gender = COALESCE(excluded.gender, athletes.gender),
            fitness_level = COALESCE(excluded.fitness_level, athletes.fitness_level),
            max_heart_rate = COALESCE(excluded.max_heart_rate, athletes.max_heart_rate),
            training_goal = COALESCE(excluded.training_goal, athletes.training_goal),
            updated_at = excluded.updated_at
        """,
        (
            name,
            email,
            row["athlete_age"],
            row["athlete_height_cm"],
            row["athlete_weight_kg"],
            row["athlete_gender"] if "athlete_gender" in row.keys() else None,
            row["athlete_fitness_level"] if "athlete_fitness_level" in row.keys() else None,
            row["athlete_max_heart_rate"] if "athlete_max_heart_rate" in row.keys() else None,
            row["athlete_training_goal"] if "athlete_training_goal" in row.keys() else None,
            now,
            now,
        ),
    )
    athlete = connection.execute(
        """
        SELECT id
        FROM athletes
        WHERE email = ?
        LIMIT 1
        """,
        (email,),
    ).fetchone()
    return int(athlete["id"]) if athlete is not None else None


def _backfill_from_sessions(
    connection: sqlite3.Connection,
    table: str,
    legacy_athlete_id: int,
) -> None:
    """Copy athlete_id from sessions into another table by session_id."""
    connection.execute(
        f"""
        UPDATE {table}
        SET athlete_id = COALESCE(
            (
                SELECT sessions.athlete_id
                FROM sessions
                WHERE sessions.session_id = {table}.session_id
                  AND sessions.athlete_id IS NOT NULL
                ORDER BY sessions.id DESC
                LIMIT 1
            ),
            ?
        )
        WHERE athlete_id IS NULL
        """,
        (legacy_athlete_id,),
    )


def _backfill_message_table_payloads(
    connection: sqlite3.Connection,
    table: str,
    legacy_athlete_id: int,
) -> None:
    """Backfill command/status rows using their stored JSON payloads."""
    rows = connection.execute(
        f"""
        SELECT id, payload, session_id, device_id, athlete_id
        FROM {table}
        WHERE session_id IS NULL
           OR athlete_id IS NULL
        """
    ).fetchall()
    for row in rows:
        payload = _parse_json_object(row["payload"])
        if payload is None:
            continue
        session_id = _non_empty_text(payload.get("session_id")) or row["session_id"]
        device_id = _non_empty_text(payload.get("device_id")) or row["device_id"]
        if not session_id:
            continue
        athlete_id = _athlete_id_from_sessions(
            connection,
            str(session_id),
            str(device_id or ""),
        )
        connection.execute(
            f"""
            UPDATE {table}
            SET session_id = COALESCE(session_id, ?),
                device_id = COALESCE(device_id, ?),
                athlete_id = COALESCE(athlete_id, ?)
            WHERE id = ?
            """,
            (
                session_id,
                device_id,
                athlete_id or legacy_athlete_id,
                row["id"],
            ),
        )


def _athlete_id_from_sessions(
    connection: sqlite3.Connection,
    session_id: str,
    device_id: str,
) -> int | None:
    """Look up an athlete ID from the sessions table."""
    filters = ["session_id = ?", "athlete_id IS NOT NULL"]
    parameters = [session_id]
    if device_id:
        filters.append("device_id = ?")
        parameters.append(device_id)
    row = connection.execute(
        f"""
        SELECT athlete_id
        FROM sessions
        WHERE {' AND '.join(filters)}
        ORDER BY id DESC
        LIMIT 1
        """,
        parameters,
    ).fetchone()
    return int(row["athlete_id"]) if row is not None else None


def _parse_json_object(payload: str) -> dict[str, object] | None:
    """Parse a payload and accept only JSON objects."""
    try:
        parsed = json.loads(str(payload))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _non_empty_text(value: object) -> str | None:
    """Return stripped text, or None for blank values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    """Return the current column names for a table."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}
