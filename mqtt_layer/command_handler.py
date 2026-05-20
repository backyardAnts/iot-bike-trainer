"""Handle MQTT command messages for the virtual bike."""

from __future__ import annotations

import json
from typing import Any


class CommandHandler:
    """Parse and apply supported commands received over MQTT."""

    def __init__(self, bike: Any) -> None:
        self.bike = bike

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

        if command == "BUZZER_ON":
            self.bike.turn_buzzer_on()
            return self._result(True, command, "Buzzer turned on")

        if command == "BUZZER_OFF":
            self.bike.turn_buzzer_off()
            return self._result(True, command, "Buzzer turned off")

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

