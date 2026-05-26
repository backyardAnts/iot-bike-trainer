"""Tests for retained active-session MQTT publishing."""

from __future__ import annotations

import json
import unittest

import backend_layer.backend_service as backend_service_module
from backend_layer.backend_service import BackendService
from backend_layer.mqtt_receiver import MqttBackendReceiver
from config_layer.mqtt_topics import SESSION_TOPIC, STATUS_TOPIC
from mqtt_layer.publisher import MqttPublisher


class SessionStatusMqttTest(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_status_messages = []
        self.original_save_status_message = backend_service_module.save_status_message
        backend_service_module.save_status_message = self._save_status_message

    def tearDown(self) -> None:
        backend_service_module.save_status_message = self.original_save_status_message

    def test_started_status_publishes_retained_active_session(self) -> None:
        receiver = MqttBackendReceiver(BackendService())
        receiver.publisher = _FakePublisher()

        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(
                STATUS_TOPIC,
                json.dumps(
                    {
                        "status": "started",
                        "device_id": "bike_001",
                        "session_id": "session_123",
                        "workout_type": "cadence",
                        "timestamp": "2026-05-26T18:00:00",
                    }
                ).encode("utf-8"),
            ),
        )

        self.assertEqual(len(self.saved_status_messages), 1)
        self.assertEqual(receiver.publisher.payloads[SESSION_TOPIC]["status"], "active")
        self.assertEqual(
            receiver.publisher.payloads[SESSION_TOPIC]["session_id"],
            "session_123",
        )
        self.assertEqual(
            receiver.publisher.payloads[SESSION_TOPIC]["workout_type"],
            "cadence",
        )
        self.assertTrue(receiver.publisher.retained[SESSION_TOPIC])

    def test_stopped_status_publishes_retained_stopped_session(self) -> None:
        receiver = MqttBackendReceiver(BackendService())
        receiver.publisher = _FakePublisher()

        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(
                STATUS_TOPIC,
                json.dumps(
                    {
                        "status": "stopped",
                        "device_id": "bike_001",
                        "session_id": "session_123",
                        "workout_type": "cadence",
                        "timestamp": "2026-05-26T18:30:00",
                    }
                ).encode("utf-8"),
            ),
        )

        session_payload = receiver.publisher.payloads[SESSION_TOPIC]
        self.assertEqual(session_payload["status"], "stopped")
        self.assertEqual(session_payload["device_id"], "bike_001")
        self.assertEqual(session_payload["session_id"], "session_123")
        self.assertEqual(session_payload["workout_type"], "cadence")
        self.assertTrue(receiver.publisher.retained[SESSION_TOPIC])

    def test_missing_session_id_status_is_saved_without_publish(self) -> None:
        receiver = MqttBackendReceiver(BackendService())
        receiver.publisher = _FakePublisher()

        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(
                STATUS_TOPIC,
                b'{"status":"started","device_id":"bike_001","workout_type":"speed"}',
            ),
        )

        self.assertEqual(len(self.saved_status_messages), 1)
        self.assertEqual(receiver.publisher.payloads, {})

    def test_invalid_status_json_is_saved_without_crashing(self) -> None:
        service = BackendService()

        session_payload = service.handle_status_message(STATUS_TOPIC, b"not json")

        self.assertIsNone(session_payload)
        self.assertEqual(
            self.saved_status_messages,
            [{"topic": STATUS_TOPIC, "payload": "not json"}],
        )

    def test_mqtt_publisher_passes_retain_for_session_publish(self) -> None:
        client = _FakeClient()
        publisher = MqttPublisher(client)

        self.assertTrue(
            publisher.publish_json(
                SESSION_TOPIC,
                {"status": "active", "session_id": "session_123"},
                retain=True,
            )
        )

        self.assertEqual(client.calls[0]["topic"], SESSION_TOPIC)
        self.assertTrue(client.calls[0]["retain"])

    def _save_status_message(self, topic: str, payload: str) -> None:
        self.saved_status_messages.append({"topic": topic, "payload": payload})


class _FakeMqttMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _FakePublisher:
    def __init__(self) -> None:
        self.payloads = {}
        self.retained = {}

    def publish_json(
        self,
        topic: str,
        payload: dict[str, object],
        retain: bool = False,
    ) -> bool:
        self.payloads[topic] = dict(payload)
        self.retained[topic] = bool(retain)
        return True


class _FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, topic: str, payload: str, retain: bool = False) -> object:
        self.calls.append(
            {
                "topic": topic,
                "payload": payload,
                "retain": bool(retain),
            }
        )
        return type("PublishResult", (), {"rc": 0})()


if __name__ == "__main__":
    unittest.main()
