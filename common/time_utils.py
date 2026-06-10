"""Timestamp helpers used by sensor messages."""

from datetime import datetime


def get_current_timestamp() -> str:
    """Return the current local timestamp in ISO 8601 format."""
    # Dropping microseconds keeps stored readings easier to read and compare.
    return datetime.now().replace(microsecond=0).isoformat()
