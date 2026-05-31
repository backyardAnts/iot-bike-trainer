"""Tests for MQTT command payload parsing."""

from __future__ import annotations

import json
import unittest

from config_layer.mqtt_topics import COMMAND_TOPIC
from mqtt_layer.command_handler import CommandHandler, parse_command_payload
from mqtt_layer.subscriber import MqttCommandSubscriber


class CommandPayloadParserTest(unittest.TestCase):
    def test_parse_command_payload_accepts_bytes(self) -> None:
        payload = _start_payload_text().encode("utf-8")

        command = parse_command_payload(payload)

        self.assertEqual(command["command"], "start_workout")
        self.assertEqual(command["workout_type"], "endurance")

    def test_parse_command_payload_accepts_bytearray(self) -> None:
        payload = bytearray(_start_payload_text().encode("utf-8"))

        command = parse_command_payload(payload)

        self.assertEqual(command["command"], "start_workout")
        self.assertEqual(command["athlete"]["age"], 20)

    def test_handler_queues_bytes_payload_from_mqtt_callback(self) -> None:
        bike = _FakeDashboardBike()
        handler = CommandHandler(bike, defer_application=True)
        subscriber = MqttCommandSubscriber(_FakeClient(), handler)

        subscriber._on_message(
            None,
            None,
            _FakeMqttMessage(COMMAND_TOPIC, _start_payload_text().encode("utf-8")),
        )

        self.assertFalse(bike.workout_active)
        result = handler.apply_latest_command()
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "started")
        self.assertTrue(bike.workout_active)
        self.assertEqual(bike.workout_type, "endurance")

    def test_handler_rejects_invalid_json_without_crashing(self) -> None:
        result = CommandHandler(_FakeDashboardBike()).handle_command(b"{not json")

        self.assertFalse(result["ok"])
        self.assertEqual(result["command"], "INVALID")


class _FakeDashboardBike:
    def __init__(self) -> None:
        self.device_id = "bike_001"
        self.session_id = ""
        self.workout_type = ""
        self.mode = "real"
        self.athlete = {}
        self.workout_active = False

    def start_workout(
        self,
        session_id: str | None = None,
        workout_type: str | None = None,
        mode: str | None = None,
        athlete: dict[str, object] | None = None,
    ) -> None:
        self.session_id = session_id or "session_test"
        self.workout_type = workout_type or ""
        self.mode = mode or self.mode
        self.athlete = dict(athlete) if isinstance(athlete, dict) else {}
        self.workout_active = True

    def is_session_active(self) -> bool:
        return self.workout_active


class _FakeClient:
    def subscribe(self, topic: str) -> tuple[int, int]:
        return (0, 1)

    def unsubscribe(self, topic: str) -> tuple[int, int]:
        return (0, 1)


class _FakeMqttMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


def _start_payload_text() -> str:
    return json.dumps(
        {
            "command": "start_workout",
            "device_id": "bike_001",
            "workout_type": "endurance",
            "mode": "real",
            "athlete": {
                "name": "Anthony",
                "age": 20,
                "weight_kg": 70,
                "height_cm": 175,
                "email": "anthony@example.com",
            },
        },
        separators=(",", ":"),
    )


if __name__ == "__main__":
    unittest.main()
