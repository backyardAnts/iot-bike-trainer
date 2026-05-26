"""Handle MQTT command messages for virtual and real bike feedback."""

from __future__ import annotations

import json
from threading import Lock
from typing import Any

from config_layer import settings

SUPPORTED_COMMANDS = {
    "BUZZER_ON",
    "BUZZER_OFF",
    "DISPLAY_MESSAGE",
    "SPEAK_MESSAGE",
    "SET_FEEDBACK",
    "UPDATE_FEEDBACK",
    "CLEAR_FEEDBACK",
    "START_SESSION",
    "STOP_SESSION",
    "SET_DISTANCE_THRESHOLD",
    "SET_HEART_RATE_LIMIT",
}


class CommandHandler:
    """Parse and apply supported commands received over MQTT."""

    def __init__(self, bike: Any, defer_application: bool = False) -> None:
        self.bike = bike
        self.defer_application = bool(defer_application)
        self._pending_command = None  # type: dict[str, Any] | None
        self._lock = Lock()

    def handle_command(self, payload: str | bytes | dict[str, Any]) -> dict[str, Any]:
        """Handle a command payload and return a command result dictionary."""
        command_data = self._parse_payload(payload)
        if command_data is None:
            return {
                "ok": False,
                "command": "INVALID",
                "message": "Command payload must be valid JSON or a dictionary",
            }

        command = str(command_data.get("command", "")).strip().upper()
        if self.defer_application:
            return self._queue_command(command, command_data)

        return self.apply_command(command_data)

    def pop_latest_command(self) -> dict[str, Any] | None:
        """Return and clear the latest queued command, if command deferral is active."""
        with self._lock:
            command_data = self._pending_command
            self._pending_command = None
        return command_data

    def apply_latest_command(self) -> dict[str, Any] | None:
        """Apply one queued command on the caller's thread."""
        command_data = self.pop_latest_command()
        if command_data is None:
            return None

        return self.apply_command(command_data)

    def apply_command(self, command_data: dict[str, Any]) -> dict[str, Any]:
        """Apply a parsed command immediately on the caller's thread."""
        command = str(command_data.get("command", "")).strip().upper()

        if command == "BUZZER_ON":
            # Legacy command: keep old clients from crashing while moving to rider feedback.
            self.bike.set_feedback(
                display_active=True,
                display_message="WARNING",
                speaker_message="Warning.",
                alert_level="warning",
                alert_side="none",
            )
            return self._result(
                True,
                command,
                "Legacy BUZZER_ON mapped to warning rider feedback",
            )

        if command == "BUZZER_OFF":
            # Legacy command: keep old clients from crashing while moving to rider feedback.
            self.bike.clear_feedback()
            return self._result(
                True,
                command,
                "Legacy BUZZER_OFF mapped to CLEAR_FEEDBACK",
            )

        if command == "DISPLAY_MESSAGE":
            message = str(command_data.get("message", ""))
            self.bike.set_display_message(message)
            return self._result(True, command, "Display message updated")

        if command == "SPEAK_MESSAGE":
            message = str(command_data.get("message", ""))
            self.bike.set_speaker_message(message)
            return self._result(True, command, "Speaker message updated")

        if command in {"SET_FEEDBACK", "UPDATE_FEEDBACK"}:
            if self._is_physical_feedback_command(command_data):
                self._apply_physical_feedback(command_data)
            else:
                self._apply_feedback(command_data)
            return self._result(
                True,
                command,
                "Rider feedback updated",
                decision_type=command_data.get("decision_type"),
                recommended_action=command_data.get("recommended_action"),
                workout_type=command_data.get("workout_type"),
                buzzer_pulse_ms=command_data.get("buzzer_pulse_ms"),
                buzzer_pulse_reason=command_data.get("buzzer_pulse_reason"),
            )

        if command == "CLEAR_FEEDBACK":
            self.bike.clear_feedback()
            return self._result(True, command, "Rider feedback cleared")

        if command == "START_SESSION":
            self._start_session()
            return self._result(True, command, "Session started")

        if command == "STOP_SESSION":
            self._stop_session()
            return self._result(True, command, "Session stopped")

        if command == "SET_DISTANCE_THRESHOLD":
            return self._result(
                True,
                command,
                "Distance threshold received but not applied yet",
                status="received_not_applied",
                value=command_data.get("value"),
            )

        if command == "SET_HEART_RATE_LIMIT":
            return self._result(
                True,
                command,
                "Heart rate limit received but not applied yet",
                status="received_not_applied",
                value=command_data.get("value"),
            )

        return self._result(False, command or "UNKNOWN", "Unsupported command")

    def _queue_command(
        self,
        command: str,
        command_data: dict[str, Any],
    ) -> dict[str, Any]:
        if command not in SUPPORTED_COMMANDS:
            return self._result(False, command or "UNKNOWN", "Unsupported command")

        with self._lock:
            self._pending_command = dict(command_data)

        return self._result(
            True,
            command,
            "Command queued for main loop",
            status="queued",
            decision_type=command_data.get("decision_type"),
            recommended_action=command_data.get("recommended_action"),
            workout_type=command_data.get("workout_type"),
            buzzer_pulse_ms=command_data.get("buzzer_pulse_ms"),
            buzzer_pulse_reason=command_data.get("buzzer_pulse_reason"),
        )

    def _parse_payload(self, payload: str | bytes | dict[str, Any]) -> dict[str, Any] | None:
        if isinstance(payload, dict):
            return payload

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None

        return None

    def _apply_feedback(self, command_data: dict[str, Any]) -> None:
        display_active = command_data.get("display_active")
        display_message = command_data.get(
            "display_message",
            getattr(self.bike, "display_message", settings.DEFAULT_DISPLAY_MESSAGE),
        )
        speaker_message = command_data.get(
            "speaker_message",
            getattr(self.bike, "speaker_message", settings.DEFAULT_SPEAKER_MESSAGE),
        )
        alert_level = command_data.get(
            "alert_level",
            getattr(self.bike, "alert_level", settings.DEFAULT_ALERT_LEVEL),
        )
        alert_side = command_data.get(
            "alert_side",
            getattr(self.bike, "alert_side", settings.DEFAULT_ALERT_SIDE),
        )
        self.bike.set_feedback(
            display_active=display_active,
            display_message=str(display_message),
            speaker_message=str(speaker_message),
            alert_level=str(alert_level),
            alert_side=str(alert_side),
        )

    def _apply_physical_feedback(self, command_data: dict[str, Any]) -> None:
        if hasattr(self.bike, "apply_physical_feedback_command"):
            self.bike.apply_physical_feedback_command(command_data)
            return

        self._apply_feedback(command_data)

    def _is_physical_feedback_command(self, command_data: dict[str, Any]) -> bool:
        physical_keys = {
            "alert_state",
            "warning_side",
            "buzzer_state",
            "led_state",
            "lcd_line_1",
            "lcd_line_2",
        }
        return any(key in command_data for key in physical_keys)

    def _start_session(self) -> None:
        if hasattr(self.bike, "start_session"):
            self.bike.start_session()
        else:
            self.bike.session_active = True

    def _stop_session(self) -> None:
        if hasattr(self.bike, "stop_session"):
            self.bike.stop_session()
        else:
            self.bike.session_active = False

    def _result(
        self,
        ok: bool,
        command: str,
        message: str,
        **extra: Any,
    ) -> dict[str, Any]:
        result = {
            "ok": ok,
            "command": command,
            "message": message,
        }
        result.update(extra)
        return result
