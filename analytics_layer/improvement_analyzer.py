"""Compare current session analytics with a previous session.

The comparison is intentionally small: it turns the main metric differences
into one sentence that can be shown in reports.
"""

from __future__ import annotations

from typing import Any


def compare_session_performance(
    current_session: dict[str, Any],
    previous_session: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a simple performance comparison summary."""
    # Without a previous ride, there is nothing fair to compare against.
    if not previous_session or previous_session.get("total_readings", 0) == 0:
        return {
            "message": "Not enough previous data",
            "average_speed_delta": None,
            "average_cadence_delta": None,
            "average_heart_rate_delta": None,
        }

    speed_delta = _round_delta(
        current_session["average_speed_kmh"]
        - previous_session["average_speed_kmh"]
    )
    cadence_delta = _round_delta(
        current_session["average_cadence_rpm"]
        - previous_session["average_cadence_rpm"]
    )
    heart_rate_delta = _round_delta(
        current_session["average_heart_rate_bpm"]
        - previous_session["average_heart_rate_bpm"]
    )

    if speed_delta > 0.5 and heart_rate_delta <= 3:
        # Faster without a large heart-rate jump is treated as improvement.
        message = "Performance improved"
    elif speed_delta < -0.5 and heart_rate_delta > 3:
        message = "Possible fatigue detected"
    else:
        message = "Performance stable"

    return {
        "message": message,
        "average_speed_delta": speed_delta,
        "average_cadence_delta": cadence_delta,
        "average_heart_rate_delta": heart_rate_delta,
    }


def _round_delta(value: float) -> float:
    """Keep comparison numbers readable in reports."""
    return round(float(value), 1)
