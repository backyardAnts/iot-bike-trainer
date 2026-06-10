"""Email-safe HTML and text templates for workout session reports.

The HTML here uses table-based layout and inline styles because many email
clients strip modern CSS.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any


GOOD_COLOR = "#16a34a"
WARNING_COLOR = "#f97316"
DANGER_COLOR = "#dc2626"
TEXT_COLOR = "#172033"
MUTED_COLOR = "#64748b"
BORDER_COLOR = "#dbe3ef"
BACKGROUND_COLOR = "#f4f7fb"
CARD_BACKGROUND = "#ffffff"


def build_session_report_email_content(report: dict[str, Any]) -> dict[str, str]:
    """Return plain-text and HTML bodies for a session report email."""
    return {
        "text_body": format_session_report_text_email(report),
        "html_body": format_session_report_html_email(report),
    }


def format_session_report_text_email(report: dict[str, Any]) -> str:
    """Return the plain-text fallback for a workout report."""
    # Plain text keeps the email readable in clients that block HTML.
    info = report["session_info"]
    performance = report["performance"]
    safety = report["safety"]
    feedback = report["feedback"]
    comparison = report["comparison"]

    lines = [
        "Bike Workout Summary",
        "",
        _build_summary_text(report),
        "",
        "Session",
        f"- Session ID: {info['session_id']}",
        f"- Device: {info['device_id']}",
        f"- Workout type: {info['workout_type'] or 'unknown'}",
        f"- Start: {info['start_timestamp'] or 'unknown'}",
        f"- End: {info['end_timestamp'] or 'unknown'}",
        f"- Duration: {info['duration']}",
        f"- Sensor readings: {info['total_sensor_readings']}",
        "",
        "Performance",
        f"- Average speed: {performance['avg_speed_kmh']} km/h",
        f"- Average cadence: {performance['avg_cadence_rpm']} rpm",
        f"- Average heart rate: {performance['avg_heart_rate_bpm']} bpm",
        f"- Max heart rate: {performance['top_heart_rate_bpm']} bpm",
        f"- Top speed: {performance['top_speed_kmh']} km/h",
        f"- Top cadence: {performance['top_cadence_rpm']} rpm",
        f"- Estimated distance: {performance['estimated_distance_km']} km",
        "",
        "Safety & Feedback",
        f"- Status: {_status_label(report)}",
        f"- Left warnings: {safety['left_warnings']}",
        f"- Right warnings: {safety['right_warnings']}",
        f"- Both-side warnings: {safety['both_warnings']}",
        f"- Total safety warnings: {safety['total_safety_warnings']}",
        f"- Danger warnings: {safety['danger_warnings']}",
        f"- High-HR workout warnings: {safety['high_hr_workout_warnings']}",
        f"- Most common action: {feedback['most_common_recommended_action']}",
        "",
        "Comparison",
        f"- {comparison['summary']}",
        _format_comparison_line("Previous", comparison["previous_session"]),
        _format_comparison_line("Average previous", comparison["previous_average"]),
        _format_comparison_line("Best previous", comparison["best_session"]),
    ]

    decisions = feedback.get("notable_decisions", [])
    if decisions:
        # Only include compact decision rows so the email does not become huge.
        lines.extend(["", "Notable DecisionEngine outputs"])
        for decision in decisions:
            lines.append(
                "- {time}: {level} / {action} / {message}".format(
                    time=decision.get("timestamp") or "unknown",
                    level=decision.get("alert_level") or "normal",
                    action=decision.get("recommended_action") or "none",
                    message=decision.get("display_message") or "No message",
                )
            )

    lines.extend(
        [
            "",
            "Detailed stats",
            f"- Easy HR zone: {_format_duration(performance['time_in_zone_easy'])}",
            f"- Moderate HR zone: {_format_duration(performance['time_in_zone_moderate'])}",
            f"- Hard HR zone: {_format_duration(performance['time_in_zone_hard'])}",
            f"- Peak HR zone: {_format_duration(performance['time_in_zone_peak'])}",
            "",
            "Heart-rate data is for training feedback only and is not a medical diagnosis.",
        ]
    )
    return "\n".join(lines)


def format_session_report_html_email(report: dict[str, Any]) -> str:
    """Return an email-safe HTML workout report."""
    # Build complex blocks first so the big template stays easier to scan.
    info = report["session_info"]
    performance = report["performance"]
    status = _status(report)
    status_color = _status_color(status)
    title = "{} Workout Summary".format(_title_case(info["workout_type"]) or "Bike")
    detail_table = _build_detail_table(report)
    decisions_html = _build_decisions_html(report)

    html = f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{BACKGROUND_COLOR};font-family:Arial,Helvetica,sans-serif;color:{TEXT_COLOR};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BACKGROUND_COLOR};margin:0;padding:24px 0;">
      <tr>
        <td align="center" style="padding:0 12px;">
          <table role="presentation" width="680" cellpadding="0" cellspacing="0" style="width:100%;max-width:680px;background:{CARD_BACKGROUND};border:1px solid {BORDER_COLOR};border-radius:14px;overflow:hidden;">
            <tr>
              <td style="background:#0f172a;padding:28px 28px 22px 28px;color:#ffffff;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="vertical-align:top;">
                      <div style="font-size:13px;letter-spacing:0;text-transform:uppercase;color:#93c5fd;font-weight:bold;">IoT Bike Trainer</div>
                      <h1 style="margin:8px 0 10px 0;font-size:28px;line-height:34px;font-weight:bold;color:#ffffff;">{_escape(title)}</h1>
                      <div style="font-size:14px;line-height:22px;color:#cbd5e1;">
                        Bike ID: <strong style="color:#ffffff;">{_escape(info["device_id"] or "unknown")}</strong><br>
                        Date/time: <strong style="color:#ffffff;">{_escape(_format_timestamp(info["start_timestamp"]) or "unknown")}</strong><br>
                        Duration: <strong style="color:#ffffff;">{_escape(info["duration"])}</strong>
                      </div>
                    </td>
                    <td align="right" style="vertical-align:top;padding-left:12px;">
                      <span style="display:inline-block;background:{status_color};color:#ffffff;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:bold;text-transform:uppercase;">{_escape(_status_label(report))}</span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 28px 8px 28px;">
                <p style="margin:0;font-size:15px;line-height:24px;color:{TEXT_COLOR};">{_escape(_build_summary_text(report))}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 22px 2px 22px;">
                {_build_metric_cards(report)}
              </td>
            </tr>
            <tr>
              <td style="padding:20px 28px 6px 28px;">
                <h2 style="margin:0 0 12px 0;font-size:20px;line-height:26px;color:{TEXT_COLOR};">Safety &amp; Feedback</h2>
                {_build_safety_html(report)}
                {decisions_html}
              </td>
            </tr>
            <tr>
              <td style="padding:18px 28px 6px 28px;">
                <h2 style="margin:0 0 12px 0;font-size:20px;line-height:26px;color:{TEXT_COLOR};">Comparison</h2>
                {_build_comparison_html(report)}
              </td>
            </tr>
            {detail_table}
            <tr>
              <td style="padding:18px 28px 28px 28px;">
                <p style="margin:0;font-size:12px;line-height:18px;color:{MUTED_COLOR};">Heart-rate data is for training feedback only and is not a medical diagnosis.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return html


def _build_metric_cards(report: dict[str, Any]) -> str:
    """Build the two-column metric card grid for the HTML report."""
    info = report["session_info"]
    performance = report["performance"]
    cards = [
        _metric_card(
            "SPD",
            "Average speed",
            _format_number(performance["avg_speed_kmh"], 1),
            "km/h",
            f"Top {_format_number(performance['top_speed_kmh'], 1)} km/h",
            GOOD_COLOR,
        ),
        _metric_card(
            "CAD",
            "Average cadence",
            _format_number(performance["avg_cadence_rpm"], 1),
            "rpm",
            f"Top {performance['top_cadence_rpm']} rpm",
            "#2563eb",
        ),
        _metric_card(
            "HR",
            "Average heart rate",
            _format_number(performance["avg_heart_rate_bpm"], 1),
            "bpm",
            f"Min {performance['min_heart_rate_bpm']} bpm",
            WARNING_COLOR,
        ),
        _metric_card(
            "MAX",
            "Max heart rate",
            str(performance["top_heart_rate_bpm"]),
            "bpm",
            "Peak session load",
            DANGER_COLOR,
        ),
    ]
    if report.get("total_sensor_readings", 0) > 0:
        cards.append(
            _metric_card(
                "KM",
                "Estimated distance",
                _format_number(performance["estimated_distance_km"], 3),
                "km",
                "Calculated from speed samples",
                "#0f766e",
            )
        )
    if info.get("duration"):
        cards.append(
            _metric_card(
                "TIME",
                "Duration",
                str(info["duration"]),
                "",
                f"{info['total_sensor_readings']} readings",
                "#7c3aed",
            )
        )
    calories = _optional_calories(report)
    if calories is not None:
        cards.append(
            _metric_card(
                "CAL",
                "Calories",
                _format_number(calories, 0),
                "kcal",
                "Estimated energy",
                "#db2777",
            )
        )

    rows = []
    for index in range(0, len(cards), 2):
        # Email clients are safest with table rows instead of flex/grid.
        left = cards[index]
        right = cards[index + 1] if index + 1 < len(cards) else _empty_card()
        rows.append(f"<tr>{left}{right}</tr>")

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        + "".join(rows)
        + "</table>"
    )


def _metric_card(
    icon: str,
    label: str,
    value: str,
    unit: str,
    helper: str,
    accent_color: str,
) -> str:
    """Return one HTML metric card cell."""
    unit_html = (
        f'<span style="font-size:14px;color:{MUTED_COLOR};font-weight:normal;"> {_escape(unit)}</span>'
        if unit
        else ""
    )
    return f"""
<td width="50%" style="padding:6px;vertical-align:top;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER_COLOR};border-radius:10px;background:#ffffff;">
    <tr>
      <td style="padding:16px;">
        <span style="display:inline-block;background:{accent_color};color:#ffffff;border-radius:8px;padding:5px 7px;font-size:11px;font-weight:bold;">{_escape(icon)}</span>
        <div style="margin-top:12px;font-size:13px;line-height:18px;color:{MUTED_COLOR};">{_escape(label)}</div>
        <div style="margin-top:4px;font-size:26px;line-height:32px;color:{TEXT_COLOR};font-weight:bold;">{_escape(value)}{unit_html}</div>
        <div style="margin-top:6px;font-size:12px;line-height:18px;color:{MUTED_COLOR};">{_escape(helper)}</div>
      </td>
    </tr>
  </table>
</td>"""


def _empty_card() -> str:
    """Return a blank cell so odd card counts still keep the table aligned."""
    return '<td width="50%" style="padding:6px;">&nbsp;</td>'


def _build_safety_html(report: dict[str, Any]) -> str:
    """Build the safety and feedback block in the HTML report."""
    safety = report["safety"]
    feedback = report["feedback"]
    status = _status(report)
    status_color = _status_color(status)
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER_COLOR};border-radius:10px;background:#ffffff;">
  <tr>
    <td style="padding:16px;">
      <div style="font-size:14px;line-height:22px;color:{TEXT_COLOR};">
        <span style="display:inline-block;background:{status_color};color:#ffffff;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:bold;">{_escape(_status_label(report))}</span>
        <span style="color:{MUTED_COLOR};margin-left:8px;">Most common action: <strong style="color:{TEXT_COLOR};">{_escape(_friendly_action(feedback["most_common_recommended_action"]))}</strong></span>
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
        <tr>
          {_safety_badge("Left", safety["left_warnings"], WARNING_COLOR)}
          {_safety_badge("Right", safety["right_warnings"], WARNING_COLOR)}
          {_safety_badge("Both", safety["both_warnings"], DANGER_COLOR)}
          {_safety_badge("Danger", safety["danger_warnings"], DANGER_COLOR)}
        </tr>
      </table>
      <div style="margin-top:12px;font-size:13px;line-height:20px;color:{MUTED_COLOR};">
        High heart-rate or workload warnings: <strong style="color:{TEXT_COLOR};">{safety["high_hr_workout_warnings"]}</strong>
      </div>
    </td>
  </tr>
</table>"""


def _safety_badge(label: str, count: int, color: str) -> str:
    """Return one warning-count badge."""
    badge_color = GOOD_COLOR if int(count) == 0 else color
    return f"""
<td width="25%" style="padding:2px 4px 2px 0;">
  <div style="border:1px solid {BORDER_COLOR};border-radius:8px;padding:10px;text-align:center;">
    <div style="font-size:18px;line-height:24px;color:{badge_color};font-weight:bold;">{int(count)}</div>
    <div style="font-size:12px;line-height:16px;color:{MUTED_COLOR};">{_escape(label)}</div>
  </div>
</td>"""


def _build_decisions_html(report: dict[str, Any]) -> str:
    """Build the notable decisions table, or a quiet empty-state line."""
    decisions = report["feedback"].get("notable_decisions", [])
    if not decisions:
        return f'<p style="margin:12px 0 0 0;font-size:13px;line-height:20px;color:{MUTED_COLOR};">No notable DecisionEngine warnings were logged for this session.</p>'

    rows = []
    for decision in decisions:
        level = str(decision.get("alert_level") or "normal").lower()
        color = _alert_color(level)
        rows.append(
            f"""
<tr>
  <td style="padding:10px 0;border-top:1px solid {BORDER_COLOR};font-size:13px;line-height:19px;color:{TEXT_COLOR};">
    <span style="display:inline-block;background:{color};color:#ffffff;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:bold;text-transform:uppercase;">{_escape(level)}</span>
    <strong style="margin-left:6px;">{_escape(_friendly_action(decision.get("recommended_action") or "none"))}</strong>
    <div style="margin-top:4px;color:{MUTED_COLOR};">{_escape(decision.get("display_message") or "No display message")} &nbsp;|&nbsp; Side: {_escape(decision.get("alert_side") or "none")} &nbsp;|&nbsp; {_escape(_format_timestamp(decision.get("timestamp") or ""))}</div>
  </td>
</tr>"""
        )

    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
  <tr>
    <td style="font-size:14px;line-height:20px;color:{TEXT_COLOR};font-weight:bold;padding-bottom:2px;">Notable DecisionEngine outputs</td>
  </tr>
  {''.join(rows)}
</table>"""


def _build_comparison_html(report: dict[str, Any]) -> str:
    """Build the comparison block against previous same-type rides."""
    comparison = report["comparison"]
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER_COLOR};border-radius:10px;background:#ffffff;">
  <tr>
    <td style="padding:16px;">
      <p style="margin:0 0 10px 0;font-size:14px;line-height:22px;color:{TEXT_COLOR};">{_escape(comparison["summary"])}</p>
      {_comparison_row("Previous", comparison["previous_session"])}
      {_comparison_row("Average previous", comparison["previous_average"])}
      {_comparison_row("Best previous", comparison["best_session"])}
    </td>
  </tr>
</table>"""


def _comparison_row(label: str, comparison: dict[str, Any]) -> str:
    """Return one HTML line of comparison deltas."""
    if comparison.get("session_id") is None:
        return f'<div style="font-size:13px;line-height:21px;color:{MUTED_COLOR};">{_escape(label)}: no data</div>'
    warning_delta = comparison["warning_count_delta"]
    warning_color = GOOD_COLOR if warning_delta <= 0 else WARNING_COLOR
    return f"""
<div style="font-size:13px;line-height:21px;color:{MUTED_COLOR};">
  <strong style="color:{TEXT_COLOR};">{_escape(label)}:</strong>
  speed {_signed(comparison["avg_speed_kmh_delta"])} km/h,
  cadence {_signed(comparison["avg_cadence_rpm_delta"])} rpm,
  HR {_signed(comparison["avg_heart_rate_bpm_delta"])} bpm,
  <span style="color:{warning_color};">warnings {_signed(warning_delta)}</span>
</div>"""


def _build_detail_table(report: dict[str, Any]) -> str:
    """Build the detailed stats table when readings exist."""
    if int(report.get("total_sensor_readings", 0)) <= 0:
        return ""

    performance = report["performance"]
    rows = [
        ("Sensor readings", str(report["total_sensor_readings"])),
        ("Top speed", f"{_format_number(performance['top_speed_kmh'], 1)} km/h"),
        ("Top cadence", f"{performance['top_cadence_rpm']} rpm"),
        ("Minimum heart rate", f"{performance['min_heart_rate_bpm']} bpm"),
        ("Easy HR zone", _format_duration(performance["time_in_zone_easy"])),
        ("Moderate HR zone", _format_duration(performance["time_in_zone_moderate"])),
        ("Hard HR zone", _format_duration(performance["time_in_zone_hard"])),
        ("Peak HR zone", _format_duration(performance["time_in_zone_peak"])),
    ]
    row_html = "".join(
        f"""
<tr>
  <td style="padding:9px 12px;border-top:1px solid {BORDER_COLOR};font-size:13px;color:{MUTED_COLOR};">{_escape(label)}</td>
  <td align="right" style="padding:9px 12px;border-top:1px solid {BORDER_COLOR};font-size:13px;color:{TEXT_COLOR};font-weight:bold;">{_escape(value)}</td>
</tr>"""
        for label, value in rows
    )
    return f"""
<tr>
  <td style="padding:18px 28px 6px 28px;">
    <h2 style="margin:0 0 12px 0;font-size:20px;line-height:26px;color:{TEXT_COLOR};">Detailed Stats</h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {BORDER_COLOR};border-radius:10px;background:#ffffff;">
      {row_html}
    </table>
  </td>
</tr>"""


def _build_summary_text(report: dict[str, Any]) -> str:
    """Build the short narrative summary at the top of the report."""
    info = report["session_info"]
    performance = report["performance"]
    safety = report["safety"]
    workout = _title_case(info["workout_type"]) or "bike"
    status = _status(report)
    summary = (
        f"You completed a {workout} session lasting {info['duration']} "
        f"with an average speed of {performance['avg_speed_kmh']} km/h, "
        f"average cadence of {performance['avg_cadence_rpm']} rpm, and "
        f"average heart rate of {performance['avg_heart_rate_bpm']} bpm."
    )
    if status == "danger":
        return (
            summary
            + f" The ride logged {safety['danger_warnings']} danger-level warning(s), "
            + "so review the safety events before the next session."
        )
    if status == "warning":
        return (
            summary
            + f" The system logged {safety['total_safety_warnings']} safety warning(s) "
            + f"and {safety['high_hr_workout_warnings']} workload warning(s)."
        )
    return summary + " No safety warnings were logged, so the session stayed in a safe operating state."


def _format_comparison_line(label: str, comparison: dict[str, Any]) -> str:
    """Return one comparison line for the plain-text email."""
    if comparison.get("session_id") is None:
        return f"- {label}: no data"
    return (
        f"- {label}: speed {comparison['avg_speed_kmh_delta']:+.1f} km/h avg, "
        f"cadence {comparison['avg_cadence_rpm_delta']:+.1f} rpm avg, "
        f"HR {comparison['avg_heart_rate_bpm_delta']:+.1f} bpm avg, "
        f"warnings {comparison['warning_count_delta']:+.1f}"
    )


def _status(report: dict[str, Any]) -> str:
    """Return the report-level status used for labels and colors."""
    safety = report["safety"]
    if int(safety["danger_warnings"]) > 0:
        return "danger"
    if int(safety["total_safety_warnings"]) > 0 or int(safety["high_hr_workout_warnings"]) > 0:
        return "warning"
    return "good"


def _status_label(report: dict[str, Any]) -> str:
    """Return the human label for the report-level status."""
    status = _status(report)
    if status == "danger":
        return "Danger"
    if status == "warning":
        return "Warning"
    return "Safe"


def _status_color(status: str) -> str:
    """Return the badge color for a report status."""
    if status == "danger":
        return DANGER_COLOR
    if status == "warning":
        return WARNING_COLOR
    return GOOD_COLOR


def _alert_color(alert_level: str) -> str:
    """Return the badge color for an individual alert level."""
    if alert_level == "danger":
        return DANGER_COLOR
    if alert_level == "warning":
        return WARNING_COLOR
    return GOOD_COLOR


def _optional_calories(report: dict[str, Any]) -> float | None:
    """Read optional calorie values when future reports include them."""
    for source in (report, report.get("performance", {})):
        if not isinstance(source, dict):
            continue
        for key in ("calories", "calories_kcal", "estimated_calories_kcal"):
            if key in source and source[key] is not None:
                try:
                    return float(source[key])
                except (TypeError, ValueError):
                    return None
    return None


def _format_timestamp(timestamp: str) -> str:
    """Format ISO timestamps for display in the email."""
    timestamp = str(timestamp).strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: int) -> str:
    """Format seconds as a compact duration string."""
    seconds = max(0, int(seconds))
    minutes, remaining_seconds = divmod(seconds, 60)
    hours, remaining_minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {remaining_minutes}m {remaining_seconds}s"
    if remaining_minutes:
        return f"{remaining_minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def _format_number(value: Any, decimals: int) -> str:
    """Format a number safely, falling back to zero on bad input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if decimals <= 0:
        return str(int(round(number)))
    return f"{number:.{decimals}f}"


def _signed(value: Any) -> str:
    """Format a signed comparison delta."""
    return f"{float(value):+.1f}"


def _friendly_action(action: Any) -> str:
    """Turn action identifiers into readable labels."""
    text = str(action).strip().replace("_", " ")
    return text.capitalize() if text else "None"


def _title_case(value: Any) -> str:
    """Return title-cased text for workout names."""
    return str(value or "").strip().replace("_", " ").title()


def _escape(value: Any) -> str:
    """Escape text before inserting it into HTML."""
    return escape(str(value), quote=True)
