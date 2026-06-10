"""Handle MQTT command messages for virtual and real bike feedback.

Commands can update rider feedback, start/stop workouts, or perform small
hardware checks. The handler accepts both old command names and newer feedback
payloads so existing clients keep working.
"""

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
    "START_WORKOUT",
    "STOP_WORKOUT",
    "TEST_BUZZER",
    "CHANGE_MODE",
    "SET_DISTANCE_THRESHOLD",
    "SET_HEART_RATE_LIMIT",
}


class CommandHandler:
    """Parse and apply supported commands received over MQTT."""

    def __init__(self, bike: Any, defer_application: bool = False) -> None:
        """Store the target bike object and decide whether commands are queued."""
        self.bike = bike
        self.defer_application = bool(defer_application)
        self._pending_command = None  # type: dict[str, Any] | None
        self._lock = Lock()

    def handle_command(
        self,
        payload: str | bytes | bytearray | dict[str, Any],
    ) -> dict[str, Any]:
        """Handle a command payload and return a command result dictionary."""
        try:
            command_data = parse_command_payload(payload)
        except ValueError:
            return {
                "ok": False,
                "command": "INVALID",
                "message": "Command payload must be valid JSON or a dictionary",
            }

        command = str(command_data.get("command", "")).strip().upper()
        # Device-specific commands should not affect other bikes on the same broker.
        if not self._is_for_this_device(command_data):
            return self._result(
                True,
                command or "UNKNOWN",
                "Command ignored for another device",
                status="ignored",
                device_id=command_data.get("device_id"),
            )
        if self.defer_application:
            # Real hardware applies commands from the main loop to avoid races.
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
            # Physical feedback commands include LCD/buzzer/LED fields.
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

        if command in {"START_SESSION", "START_WORKOUT"}:
            return self._start_workout(command, command_data)

        if command in {"STOP_SESSION", "STOP_WORKOUT"}:
            return self._stop_workout(command)

        if command == "TEST_BUZZER":
            return self._test_buzzer(command, command_data)

        if command == "CHANGE_MODE":
            return self._change_mode(command, command_data)

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
        """Store one command for the main loop to apply later."""
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

    def _apply_feedback(self, command_data: dict[str, Any]) -> None:
        """Apply generic display/speaker/alert feedback to the bike."""
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
        """Apply hardware-specific feedback when the bike supports it."""
        if hasattr(self.bike, "apply_physical_feedback_command"):
            self.bike.apply_physical_feedback_command(command_data)
            return

        self._apply_feedback(command_data)

    def _is_physical_feedback_command(self, command_data: dict[str, Any]) -> bool:
        """Return True when a command contains real-hardware feedback fields."""
        physical_keys = {
            "alert_state",
            "warning_side",
            "buzzer_state",
            "led_state",
            "lcd_line_1",
            "lcd_line_2",
        }
        return any(key in command_data for key in physical_keys)

    def _is_for_this_device(self, command_data: dict[str, Any]) -> bool:
        """Return True when the command is broadcast or addressed to this bike."""
        command_device_id = command_data.get("device_id")
        if command_device_id is None or str(command_device_id).strip() == "":
            return True

        bike_device_id = getattr(self.bike, "device_id", None)
        if bike_device_id is None:
            return True
        return str(command_device_id).strip() == str(bike_device_id)

    def _start_workout(
        self,
        command: str,
        command_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Start a workout/session on bike objects with different APIs."""
        if self._is_workout_active():
            return self._result(
                True,
                command,
                "Workout is already active",
                status="already_active",
                session_id=getattr(self.bike, "session_id", ""),
                workout_type=getattr(self.bike, "workout_type", None),
                mode=getattr(self.bike, "mode", command_data.get("mode")),
                athlete=getattr(self.bike, "athlete", {}),
                workout_active=True,
            )

        try:
            if hasattr(self.bike, "start_workout"):
                self.bike.start_workout(
                    session_id=command_data.get("session_id"),
                    workout_type=command_data.get("workout_type"),
                    mode=command_data.get("mode"),
                    athlete=command_data.get("athlete"),
                )
            elif hasattr(self.bike, "start_session"):
                self.bike.start_session()
            else:
                self.bike.session_active = True
        except ValueError as exc:
            return self._result(False, command, str(exc), status="invalid")

        return self._result(
            True,
            command,
            "Workout started",
            status="started",
            session_id=getattr(self.bike, "session_id", ""),
            workout_type=getattr(
                self.bike,
                "workout_type",
                command_data.get("workout_type"),
            ),
            mode=getattr(self.bike, "mode", command_data.get("mode")),
            athlete=getattr(self.bike, "athlete", command_data.get("athlete", {})),
            workout_active=True,
        )

    def _stop_workout(self, command: str) -> dict[str, Any]:
        """Stop a workout/session on bike objects with different APIs."""
        if not self._is_workout_active():
            return self._result(
                True,
                command,
                "No active workout to stop",
                status="idle",
                session_id=getattr(self.bike, "session_id", ""),
                workout_type=getattr(self.bike, "workout_type", None),
                mode=getattr(self.bike, "mode", None),
                athlete=getattr(self.bike, "athlete", {}),
                workout_active=False,
            )

        if hasattr(self.bike, "stop_workout"):
            self.bike.stop_workout()
        elif hasattr(self.bike, "stop_session"):
            self.bike.stop_session()
        else:
            self.bike.session_active = False

        return self._result(
            True,
            command,
            "Workout stopped",
            status="stopped",
            session_id=getattr(self.bike, "session_id", ""),
            workout_type=getattr(self.bike, "workout_type", None),
            mode=getattr(self.bike, "mode", None),
            athlete=getattr(self.bike, "athlete", {}),
            workout_active=False,
        )

    def _test_buzzer(
        self,
        command: str,
        command_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a short buzzer check when the bike has buzzer support."""
        duration_seconds = _coerce_float(command_data.get("duration_seconds"), 0.2)
        if hasattr(self.bike, "test_buzzer"):
            self.bike.test_buzzer(duration_seconds)
        elif hasattr(self.bike, "buzzer"):
            self.bike.buzzer.beep(duration_seconds)
        return self._result(
            True,
            command,
            "Buzzer test complete",
            status="buzzer_tested",
        )

    def _change_mode(
        self,
        command: str,
        command_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Switch bike mode when the target object supports it."""
        mode = str(command_data.get("mode", "")).strip()
        if not mode:
            return self._result(False, command, "Missing mode", status="invalid")

        if hasattr(self.bike, "set_mode"):
            self.bike.set_mode(mode)
        else:
            setattr(self.bike, "mode", mode)

        return self._result(
            True,
            command,
            "Mode changed",
            status="mode_changed",
            mode=getattr(self.bike, "mode", mode),
            session_id=getattr(self.bike, "session_id", ""),
            workout_type=getattr(self.bike, "workout_type", None),
            workout_active=self._is_workout_active(),
        )

    def _is_workout_active(self) -> bool:
        """Read active state across virtual, real, and fake bike objects."""
        if hasattr(self.bike, "is_session_active"):
            return bool(self.bike.is_session_active())
        if hasattr(self.bike, "workout_active"):
            return bool(self.bike.workout_active)
        return bool(getattr(self.bike, "session_active", False))

    def _result(
        self,
        ok: bool,
        command: str,
        message: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build the standard command result payload."""
        result = {
            "ok": ok,
            "command": command,
            "message": message,
        }
        result.update(extra)
        return result


def _coerce_float(value: Any, default: float) -> float:
    """Convert a command value to float with a fallback."""
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_command_payload(
    payload: str | bytes | bytearray | dict[str, Any],
) -> dict[str, Any]:
    """Parse one MQTT command payload into a dictionary."""
    # Tests can pass dictionaries directly; MQTT normally passes bytes.
    if isinstance(payload, dict):
        return payload

    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Command payload bytes must be UTF-8 JSON") from exc

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload.strip())
        except json.JSONDecodeError as exc:
            raise ValueError("Command payload string must be valid JSON") from exc
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Command payload must be valid JSON or a dictionary")
