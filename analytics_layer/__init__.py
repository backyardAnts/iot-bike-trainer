"""Session analytics helpers for the cycling trainer."""

from analytics_layer.improvement_analyzer import compare_session_performance
from analytics_layer.session_analytics import (
    calculate_latest_session_analytics,
    calculate_session_analytics,
    get_athlete_analytics,
    get_latest_session_id,
    get_previous_session_id,
)
from analytics_layer.session_report import (
    format_session_report_email,
    generate_session_report,
    process_stopped_session_report,
)
from analytics_layer.session_report_email_template import (
    build_session_report_email_content,
    format_session_report_html_email,
)

__all__ = [
    "build_session_report_email_content",
    "calculate_latest_session_analytics",
    "calculate_session_analytics",
    "compare_session_performance",
    "format_session_report_email",
    "format_session_report_html_email",
    "generate_session_report",
    "get_athlete_analytics",
    "get_latest_session_id",
    "get_previous_session_id",
    "process_stopped_session_report",
]
