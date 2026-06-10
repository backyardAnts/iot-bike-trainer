"""Reset local simulator data and recreate the SQLite schema.

Use this when local demo data is messy and the next run should start clean.
"""

from __future__ import annotations

from common.session_manager import DEFAULT_COUNTER_PATH, reset_session_counter
from database_layer.db_connection import DATABASE_PATH, initialize_database


def reset_project_data() -> None:
    """Delete local generated data and recreate an empty database."""
    # The data directory may not exist yet on a fresh checkout.
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Remember what was present so the terminal output can be honest.
    database_existed = DATABASE_PATH.exists()
    counter_existed = DEFAULT_COUNTER_PATH.exists()

    if database_existed:
        # Removing the SQLite file is enough; initialize_database recreates it.
        DATABASE_PATH.unlink()

    # Reset the generated session IDs and rebuild the schema from scratch.
    reset_session_counter()
    initialize_database()

    print("Project data reset.")
    print(f"Database recreated: {DATABASE_PATH}")
    print(f"Removed old database: {'yes' if database_existed else 'no'}")
    print(f"Removed old session counter: {'yes' if counter_existed else 'no'}")
    print("Next automatic session ID: session_001")


if __name__ == "__main__":
    reset_project_data()
