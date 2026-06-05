"""SQLite connection and initialization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "bike_trainer.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db_connection() -> sqlite3.Connection:
    """Return a SQLite connection, creating the data folder if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    """Create the SQLite database and all required tables if missing."""
    from database_layer.migrations import run_schema_migrations

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_db_connection() as connection:
        connection.executescript(schema_sql)
        run_schema_migrations(connection)
