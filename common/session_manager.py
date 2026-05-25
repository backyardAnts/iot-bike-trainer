"""Persistent session ID generation for simulator runs."""

from __future__ import annotations

from pathlib import Path
from typing import Union
## used to manage sessions

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_COUNTER_PATH = DATA_DIR / "session_counter.txt"
PathLike = Union[str, Path]


def format_session_id(number: int) -> str:
    """Return a zero-padded session ID for a positive session number."""
    session_number = int(number)
    if session_number < 1:
        raise ValueError("session number must be 1 or greater")
    return f"session_{session_number:03d}"


def read_current_session_number(counter_file: PathLike | None = None) -> int:
    """Return the last saved session number, or 0 when no counter exists."""
    counter_path = _resolve_counter_path(counter_file)
    if not counter_path.exists():
        return 0

    try:
        return max(0, int(counter_path.read_text(encoding="utf-8").strip()))
    except ValueError:
        return 0


def save_current_session_number(
    number: int,
    counter_file: PathLike | None = None,
) -> None:
    """Persist the latest generated session number."""
    counter_path = _resolve_counter_path(counter_file)
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text(f"{int(number)}\n", encoding="utf-8")


def get_next_session_id(counter_file: PathLike | None = None) -> str:
    """Increment the persistent counter and return the next session ID."""
    next_number = read_current_session_number(counter_file) + 1
    save_current_session_number(next_number, counter_file)
    return format_session_id(next_number)


def reset_session_counter(counter_file: PathLike | None = None) -> None:
    """Reset the counter so the next generated ID will be session_001."""
    counter_path = _resolve_counter_path(counter_file)
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    if counter_path.exists():
        counter_path.unlink()


def _resolve_counter_path(counter_file: PathLike | None = None) -> Path:
    return Path(counter_file) if counter_file is not None else DEFAULT_COUNTER_PATH
