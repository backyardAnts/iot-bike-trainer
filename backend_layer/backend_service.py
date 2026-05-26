"""Backend coordination for MQTT messages stored in SQLite."""

from __future__ import annotations

import json
import time
from typing import Any

from ai_decision_layer.decision_engine import DecisionEngine
from ai_decision_layer.decision_result import DecisionResult
from common.message_schema import validate_sensor_message
from common.time_utils import get_current_timestamp
from config_layer.settings import DEFAULT_SESSION_ID, DEVICE_ID
from database_layer.sqlite_storage import (
    save_command,
    save_decision_log,
    save_sensor_reading,
    save_status_message,
    start_session,
    stop_session,
)

MIN_WATCH_HEART_RATE_BPM = 30
MAX_WATCH_HEART_RATE_BPM = 240
DEFAULT_HEART_RATE_TIMEOUT_SECONDS = 10.0


class BackendService:
    """Parse MQTT payloads and store accepted records in SQLite."""

    def __init__(
        self,
        decision_engine: DecisionEngine | None = None,
        heart_rate_timeout_seconds: float = DEFAULT_HEART_RATE_TIMEOUT_SECONDS,
        monotonic_clock: Any | None = None,
    ) -> None:
        self.decision_engine = decision_engine or DecisionEngine()
        self.heart_rate_timeout_seconds = float(heart_rate_timeout_seconds)
        self._clock = monotonic_clock or time.monotonic
        self._latest_heart_rates = {}  # type: dict[tuple[str, str], dict[str, Any]]
        self._latest_merged_sensor_message = None  # type: dict[str, Any] | None

    def handle_sensor_message(
        self,
        payload: str | bytes,
        source_topic: str | None = None,
    ) -> dict[str, Any] | None:
        """Validate, save, analyze, and return an optional feedback command."""
        self._latest_merged_sensor_message = None
        payload_text = _payload_to_text(payload)
        message = _parse_json_object(payload_text)

        if message is None:
            print("Ignored invalid sensor payload: not a JSON object.")
            return None

        if not validate_sensor_message(message):
            print("Ignored invalid sensor payload: schema validation failed.")
            return None

        message = self._merge_latest_heart_rate(message)
        self._latest_merged_sensor_message = dict(message)

        save_sensor_reading(message)
        print(
            "Saved sensor reading "
            f"{message['device_id']} {message['timestamp']}."
        )

        try:
            decision = self._decide_feedback(message)
        except ValueError as exc:
            print(f"Skipped decision for invalid workout type: {exc}")
            return None

        decision_data = _decision_to_dict(decision)

        print(
            f"Decision for {message['device_id']}: {decision_data['display_message']} "
            f"| alert={decision_data['alert_level']} "
            f"| action={decision_data['recommended_action']}"
        )
        try:
            save_decision_log(message, decision, source_topic=source_topic)
            print(
                f"Saved decision log: device={message['device_id']} "
                f"session={message['session_id']} "
                f"alert={decision_data['alert_level']} "
                f"action={decision_data['recommended_action']}"
            )
        except Exception as exc:
            print(f"Failed to save decision log: {exc}")

        return build_feedback_command(decision)

    def get_latest_merged_sensor_message(self) -> dict[str, Any] | None:
        """Return the last backend-processed sensor message for MQTT output."""
        if self._latest_merged_sensor_message is None:
            return None

        message = dict(self._latest_merged_sensor_message)
        message.setdefault("buzzer_state", False)
        message.setdefault("led_state", False)
        return message

    def handle_heart_rate_message(self, payload: str | bytes) -> bool:
        """Validate and cache one Samsung Watch heart-rate MQTT payload."""
        payload_text = _payload_to_text(payload)
        message = _parse_json_object(payload_text)

        if message is None:
            print("Ignored invalid heart-rate payload: not a JSON object.")
            return False

        reading = parse_heart_rate_message(message)
        if reading is None:
            print("Ignored invalid heart-rate payload: schema validation failed.")
            return False

        key = (reading["device_id"], reading["session_id"])
        self._latest_heart_rates[key] = {
            **reading,
            "received_at_monotonic": self._clock(),
        }
        print(
            "Cached heart rate "
            f"{reading['heart_rate_bpm']} bpm for "
            f"{reading['device_id']} {reading['session_id']}."
        )
        return True

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

    def _decide_feedback(self, message: dict[str, Any]) -> DecisionResult:
        return self.decision_engine.analyze(message)

    def _merge_latest_heart_rate(self, message: dict[str, Any]) -> dict[str, Any]:
        key = (str(message["device_id"]), str(message["session_id"]))
        latest = self._latest_heart_rates.get(key)
        if latest is None:
            return message

        age_seconds = self._clock() - float(latest["received_at_monotonic"])
        if age_seconds > self.heart_rate_timeout_seconds:
            self._latest_heart_rates.pop(key, None)
            print(
                "Ignored expired heart-rate value for "
                f"{key[0]} {key[1]}: age={age_seconds:.1f}s."
            )
            return message

        merged_message = dict(message)
        merged_message["heart_rate_bpm"] = int(latest["heart_rate_bpm"])
        return merged_message


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


def parse_heart_rate_message(message: dict[str, Any]) -> dict[str, Any] | None:
    """Return a validated heart-rate reading, or None when invalid."""
    if not isinstance(message, dict):
        return None

    device_id = message.get("device_id")
    session_id = message.get("session_id")
    timestamp = message.get("timestamp")
    if not isinstance(device_id, str) or not device_id.strip():
        return None
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None

    heart_rate_bpm = _parse_heart_rate_bpm(message.get("heart_rate_bpm"))
    if heart_rate_bpm is None:
        return None

    source = message.get("source", "")
    if source is not None and not isinstance(source, str):
        return None

    return {
        "device_id": device_id,
        "session_id": session_id,
        "timestamp": timestamp,
        "heart_rate_bpm": heart_rate_bpm,
        "source": source or "",
    }


def _parse_heart_rate_bpm(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    try:
        heart_rate_bpm = int(value)
    except (TypeError, ValueError):
        return None

    if heart_rate_bpm < MIN_WATCH_HEART_RATE_BPM:
        return None
    if heart_rate_bpm > MAX_WATCH_HEART_RATE_BPM:
        return None
    return heart_rate_bpm


def build_feedback_command(decision: DecisionResult | dict[str, Any]) -> dict[str, Any]:
    """Build an MQTT command payload from a decision result."""
    decision_data = _decision_to_dict(decision)
    command = {
        "command": "update_feedback",
        "display_active": decision_data["display_active"],
        "display_message": decision_data["display_message"],
        "speaker_message": decision_data["speaker_message"],
        "alert_level": decision_data["alert_level"],
        "alert_side": decision_data["alert_side"],
        "decision_type": decision_data["decision_type"],
        "recommended_action": decision_data["recommended_action"],
        "workout_type": decision_data["workout_type"],
    }
    for key in (
        "alert_state",
        "warning_side",
        "buzzer_state",
        "led_state",
        "buzzer_pulse_ms",
        "buzzer_pulse_reason",
        "lcd_line_1",
        "lcd_line_2",
        "heart_rate_bpm",
        "hr_percent",
    ):
        if key == "hr_percent" and decision_data.get(key) is None:
            continue
        if key in decision_data:
            command[key] = decision_data[key]
    return command


def _decision_to_dict(decision: DecisionResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(decision, dict):
        return decision
    return decision.to_dict()
