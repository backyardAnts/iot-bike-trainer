"""Backend coordination for MQTT messages stored in SQLite."""

from __future__ import annotations

import json
from typing import Any

from common.message_schema import validate_sensor_message
from common.time_utils import get_current_timestamp
from config_layer.settings import DEFAULT_SESSION_ID, DEVICE_ID
from database_layer.sqlite_storage import (
    save_command,
    save_sensor_reading,
    save_status_message,
    start_session,
    stop_session,
)


class BackendService:
    """Parse MQTT payloads and store accepted records in SQLite."""

    def handle_sensor_message(self, payload: str | bytes) -> None:
        """Validate and save one sensor reading payload."""
        payload_text = _payload_to_text(payload)
        message = _parse_json_object(payload_text)

        if message is None:
            print("Ignored invalid sensor payload: not a JSON object.")
            return

        if not validate_sensor_message(message):
            print("Ignored invalid sensor payload: schema validation failed.")
            return

        save_sensor_reading(message)
        print(
            "Saved sensor reading "
            f"{message['device_id']} {message['timestamp']}."
        )

    def handle_status_message(self, topic: str, payload: str | bytes) -> None:
        """Save one raw status payload."""
        payload_text = _payload_to_text(payload)
        save_status_message(topic, payload_text)
        print(f"Saved status message from {topic}: {payload_text}")

    def handle_command_message(self, payload: str | bytes) -> None:
        """Save one command payload and update session rows when applicable."""
        payload_text = _payload_to_text(payload)
        command_payload = _parse_json_object(payload_text)

        save_command(command_payload if command_payload is not None else payload_text)

        if command_payload is None:
            print(f"Saved non-JSON command payload: {payload_text}")
            return

        command = str(command_payload.get("command", "")).strip().upper()
        if command == "START_SESSION":
            self._start_session_from_command(command_payload)
        elif command == "STOP_SESSION":
            self._stop_session_from_command(command_payload)

        print(f"Saved command message: {command or 'UNKNOWN'}")

    def _start_session_from_command(self, command_payload: dict[str, Any]) -> None:
        session_id = str(command_payload.get("session_id", DEFAULT_SESSION_ID))
        device_id = str(command_payload.get("device_id", DEVICE_ID))
        start_time = str(command_payload.get("timestamp", get_current_timestamp()))
        start_session(session_id, device_id, start_time)
        print(f"Started session record: {session_id}")

    def _stop_session_from_command(self, command_payload: dict[str, Any]) -> None:
        session_id = str(command_payload.get("session_id", DEFAULT_SESSION_ID))
        end_time = str(command_payload.get("timestamp", get_current_timestamp()))
        stop_session(session_id, end_time)
        print(f"Stopped session record: {session_id}")


def _payload_to_text(payload: str | bytes) -> str:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return str(payload)


def _parse_json_object(payload: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None
