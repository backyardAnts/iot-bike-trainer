"""Backend coordination for MQTT messages stored in SQLite."""

from __future__ import annotations

import json
import time
from typing import Any

from analytics_layer.session_report import process_stopped_session_report
from ai_decision_layer.decision_engine import DecisionEngine
from ai_decision_layer.decision_result import DecisionResult
from common.message_schema import validate_sensor_message
from common.time_utils import get_current_timestamp
from config_layer.rider_profile import get_default_rider_profile
from config_layer.settings import DEFAULT_SESSION_ID, DEVICE_ID
from database_layer.sqlite_storage import (
    save_command,
    save_decision_log,
    save_sensor_reading,
    save_session_metadata,
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
        self._uses_default_decision_engine = decision_engine is None
        self.decision_engine = decision_engine or DecisionEngine()
        self.heart_rate_timeout_seconds = float(heart_rate_timeout_seconds)
        self._clock = monotonic_clock or time.monotonic
        self._latest_heart_rates = {}  # type: dict[tuple[str, str], dict[str, Any]]
        self._latest_merged_sensor_message = None  # type: dict[str, Any] | None
        self._session_context = {}  # type: dict[tuple[str, str], dict[str, Any]]

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

    def handle_status_message(
        self,
        topic: str,
        payload: str | bytes,
    ) -> dict[str, Any] | None:
        """Save one raw status payload and return a session update when present."""
        payload_text = _payload_to_text(payload)
        save_status_message(topic, payload_text)
        print(f"Saved status message from {topic}: {payload_text}")
        status_message = _parse_json_object(payload_text)
        if status_message is None:
            return None
        self._cache_session_context_from_status(status_message)
        session_payload = build_session_status_payload(status_message)
        if session_payload is None:
            return None

        self._update_session_record_from_status(session_payload)
        if session_payload["status"] == "stopped":
            self._send_stopped_session_report(session_payload)
        return session_payload

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

    def _update_session_record_from_status(self, session_payload: dict[str, Any]) -> None:
        session_id = str(session_payload["session_id"])
        timestamp = str(session_payload["timestamp"])
        if session_payload["status"] == "active":
            start_session(session_id, str(session_payload["device_id"]), timestamp)
            self._save_session_metadata_from_payload(session_payload)
            return

        self._save_session_metadata_from_payload(session_payload)
        stop_session(session_id, timestamp)

    def _send_stopped_session_report(self, session_payload: dict[str, Any]) -> None:
        try:
            process_stopped_session_report(session_payload)
        except Exception as exc:
            print(
                "Failed to process stopped-session report for "
                f"{session_payload.get('session_id')}: {exc}"
            )

    def _decide_feedback(self, message: dict[str, Any]) -> DecisionResult:
        rider_profile = self._rider_profile_for_message(message)
        if rider_profile is not None and (
            self._uses_default_decision_engine
            or isinstance(self.decision_engine, DecisionEngine)
        ):
            return DecisionEngine(rider_profile=rider_profile).analyze(message)
        return self.decision_engine.analyze(message)

    def _cache_session_context_from_status(self, status_message: dict[str, Any]) -> None:
        status = str(status_message.get("status", "")).strip().lower()
        if status not in {"started", "stopped"}:
            return

        session_id = _non_empty_string(status_message.get("session_id"))
        if session_id is None:
            return

        device_id = _non_empty_string(status_message.get("device_id")) or DEVICE_ID
        athlete = _clean_athlete(status_message.get("athlete"))
        context = dict(self._session_context.get((device_id, session_id), {}))
        if athlete:
            context["athlete"] = athlete
        workout_type = _non_empty_string(status_message.get("workout_type"))
        if workout_type:
            context["workout_type"] = workout_type
        mode = _non_empty_string(status_message.get("mode"))
        if mode:
            context["mode"] = mode
        if context:
            self._session_context[(device_id, session_id)] = context

    def _rider_profile_for_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        key = (str(message["device_id"]), str(message["session_id"]))
        context = self._session_context.get(key)
        if not context:
            return None

        athlete = context.get("athlete")
        if not isinstance(athlete, dict):
            return None

        age = _parse_positive_int(athlete.get("age"))
        if age is None:
            return None

        rider_profile = get_default_rider_profile()
        rider_profile["age"] = age
        rider_profile["weight_kg"] = _parse_positive_float(
            athlete.get("weight_kg"),
            rider_profile.get("weight_kg", 75),
        )
        return rider_profile

    def _save_session_metadata_from_payload(
        self,
        session_payload: dict[str, Any],
    ) -> None:
        athlete = session_payload.get("athlete")
        if not isinstance(athlete, dict) or not athlete:
            return

        try:
            save_session_metadata(
                str(session_payload["session_id"]),
                device_id=str(session_payload.get("device_id", "")),
                workout_type=str(session_payload.get("workout_type", "")),
                mode=str(session_payload.get("mode", "")),
                athlete=athlete,
            )
        except Exception as exc:
            print(
                "Failed to save session athlete metadata for "
                f"{session_payload.get('session_id')}: {exc}"
            )

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


def build_session_status_payload(
    status_message: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a retained session-topic payload for started/stopped bike status."""
    status = str(status_message.get("status", "")).strip().lower()
    if status == "ready":
        return None
    if status not in {"started", "stopped"}:
        return None

    session_id = _non_empty_string(status_message.get("session_id"))
    if session_id is None:
        return None

    device_id = _non_empty_string(status_message.get("device_id"))
    if status == "started":
        if device_id != DEVICE_ID:
            return None
    elif device_id is None:
        device_id = DEVICE_ID
    elif device_id != DEVICE_ID:
        return None

    timestamp = _non_empty_string(status_message.get("timestamp"))
    workout_type = _non_empty_string(status_message.get("workout_type")) or ""
    payload = {
        "device_id": device_id,
        "session_id": session_id,
        "workout_type": workout_type,
        "status": "active" if status == "started" else "stopped",
        "timestamp": timestamp or get_current_timestamp(),
    }
    mode = _non_empty_string(status_message.get("mode"))
    if mode:
        payload["mode"] = mode
    athlete = _clean_athlete(status_message.get("athlete"))
    if athlete:
        payload["athlete"] = athlete
    return payload


def _non_empty_string(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _clean_athlete(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    athlete = {}
    for key in ("name", "email"):
        text = _non_empty_string(value.get(key))
        if text is not None:
            athlete[key] = text

    for key in ("age", "weight_kg", "height_cm"):
        if key in value:
            athlete[key] = value[key]

    return athlete


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _parse_positive_float(value: Any, default: Any) -> float:
    if isinstance(value, bool):
        return float(default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if number > 0 else float(default)


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
