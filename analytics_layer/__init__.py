"""Session analytics helpers for the cycling trainer."""

from analytics_layer.improvement_analyzer import compare_session_performance
from analytics_layer.session_analytics import (
    calculate_latest_session_analytics,
    calculate_session_analytics,
    get_latest_session_id,
    get_previous_session_id,
)
from analytics_layer.session_report import (
    format_session_report_email,
    generate_session_report,
    process_stopped_session_report,
)

__all__ = [
    "calculate_latest_session_analytics",
    "calculate_session_analytics",
    "compare_session_performance",
    "format_session_report_email",
    "generate_session_report",
    "get_latest_session_id",
    "get_previous_session_id",
    "process_stopped_session_report",
]
