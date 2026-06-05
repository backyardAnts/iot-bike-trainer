"""Build and send session analytics reports when workouts stop."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import inspect
from statistics import mean
from typing import Any

from analytics_layer.email_sender import send_session_report_email
from analytics_layer.session_report_email_template import (
    build_session_report_email_content,
    format_session_report_text_email,
)
from database_layer.db_connection import get_db_connection
from database_layer.sqlite_storage import (
    get_session_report_email_record,
    reserve_session_report_email,
    save_session_analytics,
    update_session_report_email_result,
)


URGENT_WORKOUT_ACTIONS = {
    "recover",
    "reduce_speed",
    "slow_cadence",
    "reduce_effort",
    "near_limit",
}
TRACKED_FEEDBACK_ACTIONS = {
    "recover",
    "reduce_speed",
    "slow_cadence",
    "reduce_effort",
    "increase_speed",
    "pedal_faster",
    "keep_cadence",
    "maintain_pace",
}


def process_stopped_session_report(
    session_payload: dict[str, Any],
    email_sender: Any = send_session_report_email,
) -> dict[str, Any] | None:
    """Generate, save, and email one stopped-session report exactly once."""
    session_id = _non_empty_string(session_payload.get("session_id"))
    if session_id is None:
        return None

    if get_session_report_email_record(session_id) is not None:
        print(f"Workout report already processed for {session_id}; skipping email.")
        return {
            "session_id": session_id,
            "skipped_duplicate": True,
        }

    report = generate_session_report(session_id, stopped_status=session_payload)
    subject = build_session_report_subject(report)
    email_content = build_session_report_email_content(report)
    body = email_content["text_body"]
    html_body = email_content["html_body"]

    if not reserve_session_report_email(
        session_id,
        str(report["workout_type"]),
        subject,
        body,
    ):
        print(f"Workout report already reserved for {session_id}; skipping email.")
        return {
            "session_id": session_id,
            "skipped_duplicate": True,
        }

    try:
        save_session_analytics(report)
    except Exception as exc:
        print(f"Failed to save session analytics for {session_id}: {exc}")

    try:
        email_result = _send_report_email(
            email_sender,
            subject,
            body,
            html_body,
        )
    except Exception as exc:
        email_result = {
            "status": "failed",
            "sent": False,
            "email_to": "",
            "error": str(exc),
        }
        print(f"Failed to send workout report email for {session_id}: {exc}")

    update_session_report_email_result(
        session_id,
        str(email_result.get("status", "failed")),
        str(email_result.get("email_to", "")),
        str(email_result.get("error", "")),
    )
    return {
        "session_id": session_id,
        "report": report,
        "email": email_result,
    }


def generate_session_report(
    session_id: str,
    stopped_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate a complete report for one stopped session."""
    current = _calculate_session_metrics(session_id, stopped_status)
    comparison = _build_same_workout_comparison(current)
    current["comparison"] = comparison
    current["improvement_vs_previous_session"] = comparison["summary"]
    current["improvement_details"] = comparison
    return current


def build_session_report_subject(report: dict[str, Any]) -> str:
    """Return the workout report email subject."""
    return "Bike Workout Summary - {} - {}".format(
        report["session_id"],
        report["workout_type"] or "unknown",
    )


def format_session_report_email(report: dict[str, Any]) -> str:
    """Return a readable plain-text workout report."""
    return format_session_report_text_email(report)


def _send_report_email(
    email_sender: Any,
    subject: str,
    body: str,
    html_body: str,
) -> dict[str, Any]:
    """Send a report while preserving compatibility with two-argument senders."""
    try:
        signature = inspect.signature(email_sender)
    except (TypeError, ValueError):
        return email_sender(subject, body, html_body)

    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return email_sender(subject, body, html_body)

    parameters = signature.parameters.values()
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return email_sender(subject, body, html_body=html_body)

    parameters_by_name = signature.parameters
    if "html_body" in parameters_by_name:
        return email_sender(subject, body, html_body=html_body)

    positional_count = sum(
        1
        for parameter in parameters_by_name.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    )
    if positional_count >= 3:
        return email_sender(subject, body, html_body)

    return email_sender(subject, body)


def _calculate_session_metrics(
    session_id: str,
    stopped_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readings = _load_readings_for_session(session_id)
    decisions = _load_decision_logs_for_session(session_id)
    session_row = _load_session_row(session_id)
    sample_seconds = _estimate_sample_seconds(readings)
    info = _build_session_info(
        session_id,
        readings,
        decisions,
        session_row,
        stopped_status,
        sample_seconds,
    )
    performance = _calculate_performance(readings, sample_seconds)
    safety = _calculate_safety(readings, decisions)
    feedback = _calculate_feedback(decisions)

    return {
        "session_id": session_id,
        "device_id": info["device_id"],
        "workout_type": info["workout_type"],
        "start_timestamp": info["start_timestamp"],
        "end_timestamp": info["end_timestamp"],
        "duration_seconds": info["duration_seconds"],
        "total_sensor_readings": info["total_sensor_readings"],
        "session_info": info,
        "performance": performance,
        "safety": safety,
        "feedback": feedback,
        "top_speed_kmh": performance["top_speed_kmh"],
        "avg_speed_kmh": performance["avg_speed_kmh"],
        "average_speed_kmh": performance["avg_speed_kmh"],
        "top_cadence_rpm": performance["top_cadence_rpm"],
        "avg_cadence_rpm": performance["avg_cadence_rpm"],
        "average_cadence_rpm": performance["avg_cadence_rpm"],
        "top_heart_rate_bpm": performance["top_heart_rate_bpm"],
        "avg_heart_rate_bpm": performance["avg_heart_rate_bpm"],
        "average_heart_rate_bpm": performance["avg_heart_rate_bpm"],
        "max_heart_rate_bpm": performance["top_heart_rate_bpm"],
        "min_heart_rate_bpm": performance["min_heart_rate_bpm"],
        "estimated_distance_km": performance["estimated_distance_km"],
        "total_readings": info["total_sensor_readings"],
        "session_duration_seconds": info["duration_seconds"],
        "time_in_zone_easy": performance["time_in_zone_easy"],
        "time_in_zone_moderate": performance["time_in_zone_moderate"],
        "time_in_zone_hard": performance["time_in_zone_hard"],
        "time_in_zone_peak": performance["time_in_zone_peak"],
        "improvement_vs_previous_session": "No previous same-type workout data",
    }


def _build_session_info(
    session_id: str,
    readings: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    session_row: dict[str, Any] | None,
    stopped_status: dict[str, Any] | None,
    sample_seconds: int,
) -> dict[str, Any]:
    first_reading = readings[0] if readings else {}
    last_reading = readings[-1] if readings else {}
    device_id = (
        _status_value(stopped_status, "device_id")
        or _non_empty_string(session_row.get("device_id") if session_row else None)
        or _non_empty_string(first_reading.get("device_id"))
        or ""
    )
    workout_type = (
        _status_value(stopped_status, "workout_type")
        or _most_common_workout_type(decisions)
        or ""
    )
    start_timestamp = (
        _non_empty_string(session_row.get("start_time") if session_row else None)
        or _non_empty_string(first_reading.get("timestamp"))
        or ""
    )
    end_timestamp = (
        _status_value(stopped_status, "timestamp")
        or _non_empty_string(session_row.get("end_time") if session_row else None)
        or _non_empty_string(last_reading.get("timestamp"))
        or start_timestamp
    )
    duration_seconds = _calculate_duration_seconds(
        readings,
        start_timestamp,
        end_timestamp,
        sample_seconds,
    )
    return {
        "session_id": session_id,
        "device_id": device_id,
        "workout_type": workout_type,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "duration_seconds": duration_seconds,
        "duration": _format_duration(duration_seconds),
        "total_sensor_readings": len(readings),
    }


def _calculate_performance(
    readings: list[dict[str, Any]],
    sample_seconds: int,
) -> dict[str, Any]:
    if not readings:
        return {
            "top_speed_kmh": 0.0,
            "avg_speed_kmh": 0.0,
            "top_cadence_rpm": 0,
            "avg_cadence_rpm": 0.0,
            "top_heart_rate_bpm": 0,
            "avg_heart_rate_bpm": 0.0,
            "min_heart_rate_bpm": 0,
            "estimated_distance_km": 0.0,
            "time_in_zone_easy": 0,
            "time_in_zone_moderate": 0,
            "time_in_zone_hard": 0,
            "time_in_zone_peak": 0,
        }

    speeds = [_to_float(reading.get("speed_kmh"), 0.0) for reading in readings]
    cadences = [_to_int(reading.get("cadence_rpm"), 0) for reading in readings]
    heart_rates = [
        _to_int(reading.get("heart_rate_bpm"), 0)
        for reading in readings
        if _is_valid_heart_rate(reading.get("heart_rate_bpm"))
    ]
    zone_counts = _count_heart_rate_zones(heart_rates)
    return {
        "top_speed_kmh": round(max(speeds), 1),
        "avg_speed_kmh": round(mean(speeds), 1),
        "top_cadence_rpm": max(cadences),
        "avg_cadence_rpm": round(mean(cadences), 1),
        "top_heart_rate_bpm": max(heart_rates) if heart_rates else 0,
        "avg_heart_rate_bpm": round(mean(heart_rates), 1) if heart_rates else 0.0,
        "min_heart_rate_bpm": min(heart_rates) if heart_rates else 0,
        "estimated_distance_km": _estimate_distance_km(speeds, sample_seconds),
        "time_in_zone_easy": int(zone_counts["easy"] * sample_seconds),
        "time_in_zone_moderate": int(zone_counts["moderate"] * sample_seconds),
        "time_in_zone_hard": int(zone_counts["hard"] * sample_seconds),
        "time_in_zone_peak": int(zone_counts["peak"] * sample_seconds),
    }


def _calculate_safety(
    readings: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, int]:
    source = decisions if decisions else readings
    left = _count_warning_side(source, "left")
    right = _count_warning_side(source, "right")
    both = _count_warning_side(source, "both")
    return {
        "left_warnings": left,
        "right_warnings": right,
        "both_warnings": both,
        "total_safety_warnings": left + right + both,
        "danger_warnings": sum(
            1 for item in source if str(item.get("alert_level", "")).lower() == "danger"
        ),
        "high_hr_workout_warnings": sum(
            1
            for decision in decisions
            if str(decision.get("recommended_action", "")).lower()
            in URGENT_WORKOUT_ACTIONS
        ),
    }


def _calculate_feedback(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    actions = [
        str(decision.get("recommended_action", "")).strip().lower()
        for decision in decisions
        if str(decision.get("recommended_action", "")).strip()
    ]
    action_counts = Counter(actions)
    most_common = action_counts.most_common(1)
    feedback = {
        "most_common_recommended_action": most_common[0][0] if most_common else "none",
        "action_counts": dict(action_counts),
        "notable_decisions": _select_notable_decisions(decisions),
    }
    for action in TRACKED_FEEDBACK_ACTIONS:
        feedback[f"{action}_count"] = int(action_counts.get(action, 0))
    return feedback


def _select_notable_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a compact set of DecisionEngine outputs for the email report."""
    notable = []
    routine_actions = {
        "",
        "none",
        "keep_cadence",
        "maintain_pace",
        "maintain_speed",
    }
    for decision in decisions:
        alert_level = str(decision.get("alert_level", "")).strip().lower()
        recommended_action = (
            str(decision.get("recommended_action", "")).strip().lower()
        )
        display_message = str(decision.get("display_message", "")).strip()
        if not recommended_action and not display_message:
            continue
        if alert_level not in {"warning", "danger"} and recommended_action in routine_actions:
            continue
        notable.append(_compact_decision(decision))

    if not notable and decisions:
        notable = [_compact_decision(decision) for decision in decisions[-3:]]

    return notable[-5:]


def _compact_decision(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": str(decision.get("timestamp", "")),
        "decision_type": str(decision.get("decision_type", "")),
        "alert_level": str(decision.get("alert_level", "normal")),
        "alert_side": str(decision.get("alert_side", "none")),
        "display_message": str(decision.get("display_message", "")),
        "speaker_message": str(decision.get("speaker_message", "")),
        "recommended_action": str(decision.get("recommended_action", "none")),
    }


def _build_same_workout_comparison(current: dict[str, Any]) -> dict[str, Any]:
    workout_type = str(current.get("workout_type", ""))
    previous_session_ids = _list_previous_session_ids_same_workout(
        str(current["session_id"]),
        workout_type,
    )
    previous_reports = [
        _calculate_session_metrics(previous_session_id)
        for previous_session_id in previous_session_ids
    ]
    previous_reports = [
        report for report in previous_reports if report["total_sensor_readings"] > 0
    ]
    if not previous_reports:
        empty = _empty_comparison()
        return {
            "summary": "No previous same-type workout data",
            "previous_session": empty,
            "previous_average": empty,
            "best_session": empty,
            "previous_session_count": 0,
        }

    previous = previous_reports[0]
    previous_average = _average_report(previous_reports)
    best = max(
        previous_reports,
        key=lambda report: (
            report["performance"]["top_speed_kmh"],
            report["performance"]["avg_speed_kmh"],
        ),
    )
    previous_comparison = _compare_reports(current, previous)
    summary = "Compared with previous {} workout {}".format(
        workout_type or "same-type",
        previous["session_id"],
    )
    return {
        "summary": summary,
        "previous_session": previous_comparison,
        "previous_average": _compare_reports(current, previous_average),
        "best_session": _compare_reports(current, best),
        "previous_session_count": len(previous_reports),
    }


def _average_report(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "session_id": "average_previous",
        "performance": {
            metric: round(mean(report["performance"][metric] for report in reports), 1)
            for metric in (
                "top_speed_kmh",
                "avg_speed_kmh",
                "top_cadence_rpm",
                "avg_cadence_rpm",
                "top_heart_rate_bpm",
                "avg_heart_rate_bpm",
            )
        },
        "safety": {
            "total_safety_warnings": round(
                mean(report["safety"]["total_safety_warnings"] for report in reports),
                1,
            )
        },
    }


def _compare_reports(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    return {
        "session_id": baseline.get("session_id"),
        "top_speed_kmh_delta": _delta(
            current["performance"]["top_speed_kmh"],
            baseline["performance"]["top_speed_kmh"],
        ),
        "avg_speed_kmh_delta": _delta(
            current["performance"]["avg_speed_kmh"],
            baseline["performance"]["avg_speed_kmh"],
        ),
        "top_cadence_rpm_delta": _delta(
            current["performance"]["top_cadence_rpm"],
            baseline["performance"]["top_cadence_rpm"],
        ),
        "avg_cadence_rpm_delta": _delta(
            current["performance"]["avg_cadence_rpm"],
            baseline["performance"]["avg_cadence_rpm"],
        ),
        "top_heart_rate_bpm_delta": _delta(
            current["performance"]["top_heart_rate_bpm"],
            baseline["performance"]["top_heart_rate_bpm"],
        ),
        "avg_heart_rate_bpm_delta": _delta(
            current["performance"]["avg_heart_rate_bpm"],
            baseline["performance"]["avg_heart_rate_bpm"],
        ),
        "warning_count_delta": _delta(
            current["safety"]["total_safety_warnings"],
            baseline["safety"]["total_safety_warnings"],
        ),
    }


def _format_comparison_line(label: str, comparison: dict[str, Any]) -> str:
    if comparison.get("session_id") is None:
        return f"- {label}: no data"
    return (
        f"- {label}: speed {comparison['avg_speed_kmh_delta']:+.1f} km/h avg, "
        f"cadence {comparison['avg_cadence_rpm_delta']:+.1f} rpm avg, "
        f"HR {comparison['avg_heart_rate_bpm_delta']:+.1f} bpm avg, "
        f"warnings {comparison['warning_count_delta']:+.1f}"
    )


def _empty_comparison() -> dict[str, Any]:
    return {
        "session_id": None,
        "top_speed_kmh_delta": None,
        "avg_speed_kmh_delta": None,
        "top_cadence_rpm_delta": None,
        "avg_cadence_rpm_delta": None,
        "top_heart_rate_bpm_delta": None,
        "avg_heart_rate_bpm_delta": None,
        "warning_count_delta": None,
    }


def _load_readings_for_session(session_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM sensor_readings
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def _load_decision_logs_for_session(session_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM decision_logs
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def _load_session_row(session_id: str) -> dict[str, Any] | None:
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM sessions
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    return dict(row) if row is not None else None


def _list_previous_session_ids_same_workout(
    current_session_id: str,
    workout_type: str,
) -> list[str]:
    if not workout_type:
        return []

    current_first_id = _get_first_reading_id(current_session_id)
    latest_allowed_id = current_first_id if current_first_id is not None else 10**18
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT sr.session_id, MAX(sr.id) AS latest_reading_id
            FROM sensor_readings sr
            WHERE sr.session_id != ?
              AND EXISTS (
                  SELECT 1
                  FROM decision_logs dl
                  WHERE dl.session_id = sr.session_id
                    AND dl.workout_type = ?
              )
            GROUP BY sr.session_id
            HAVING MAX(sr.id) < ?
            ORDER BY latest_reading_id DESC
            """,
            (current_session_id, workout_type, latest_allowed_id),
        ).fetchall()

    return [str(row["session_id"]) for row in rows]


def _get_first_reading_id(session_id: str) -> int | None:
    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT MIN(id) AS first_reading_id
            FROM sensor_readings
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()

    if row is None or row["first_reading_id"] is None:
        return None
    return int(row["first_reading_id"])


def _count_warning_side(items: list[dict[str, Any]], side: str) -> int:
    count = 0
    for item in items:
        alert_side = str(item.get("alert_side", "")).strip().lower()
        recommended_action = str(item.get("recommended_action", "")).strip().lower()
        alert_level = str(item.get("alert_level", "")).strip().lower()
        if recommended_action == f"object_{side}":
            count += 1
        elif alert_side == side and alert_level in {"warning", "danger"}:
            count += 1
    return count


def _most_common_workout_type(decisions: list[dict[str, Any]]) -> str | None:
    workout_types = [
        str(decision.get("workout_type", "")).strip()
        for decision in decisions
        if str(decision.get("workout_type", "")).strip()
    ]
    if not workout_types:
        return None
    return Counter(workout_types).most_common(1)[0][0]


def _estimate_distance_km(speeds: list[float], sample_seconds: int) -> float:
    if not speeds:
        return 0.0
    distance = sum(speed * (sample_seconds / 3600.0) for speed in speeds)
    return round(distance, 3)


def _estimate_sample_seconds(readings: list[dict[str, Any]]) -> int:
    timestamps = _parse_reading_timestamps(readings)
    intervals = [
        int((timestamps[index] - timestamps[index - 1]).total_seconds())
        for index in range(1, len(timestamps))
        if timestamps[index] > timestamps[index - 1]
    ]
    if not intervals:
        return 1
    return max(1, round(mean(intervals)))


def _calculate_duration_seconds(
    readings: list[dict[str, Any]],
    start_timestamp: str,
    end_timestamp: str,
    sample_seconds: int,
) -> int:
    start = _parse_timestamp(start_timestamp)
    end = _parse_timestamp(end_timestamp)
    if start is not None and end is not None and end >= start:
        return int((end - start).total_seconds())
    return len(readings) * sample_seconds


def _parse_reading_timestamps(readings: list[dict[str, Any]]) -> list[datetime]:
    timestamps = []
    for reading in readings:
        parsed = _parse_timestamp(str(reading.get("timestamp", "")))
        if parsed is not None:
            timestamps.append(parsed)
    return timestamps


def _parse_timestamp(timestamp: str) -> datetime | None:
    timestamp = str(timestamp).strip()
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _count_heart_rate_zones(heart_rates: list[int]) -> dict[str, int]:
    zone_counts = {
        "easy": 0,
        "moderate": 0,
        "hard": 0,
        "peak": 0,
    }
    for heart_rate in heart_rates:
        if heart_rate < 120:
            zone_counts["easy"] += 1
        elif heart_rate < 150:
            zone_counts["moderate"] += 1
        elif heart_rate < 170:
            zone_counts["hard"] += 1
        else:
            zone_counts["peak"] += 1
    return zone_counts


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"
    if remaining_minutes:
        return f"{remaining_minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _status_value(status: dict[str, Any] | None, key: str) -> str | None:
    if status is None:
        return None
    return _non_empty_string(status.get(key))


def _non_empty_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_valid_heart_rate(value: Any) -> bool:
    heart_rate = _to_int(value, 0)
    return 40 <= heart_rate <= 220


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _delta(current_value: Any, baseline_value: Any) -> float:
    return round(float(current_value) - float(baseline_value), 1)
