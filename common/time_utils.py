"""Timestamp helpers used by sensor messages."""

from datetime import datetime


## to get the timestamp... obviously
def get_current_timestamp() -> str:
    """Return the current local timestamp in ISO 8601 format."""
    return datetime.now().replace(microsecond=0).isoformat()
