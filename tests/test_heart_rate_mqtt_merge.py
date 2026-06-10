"""Tests for Samsung Watch heart-rate MQTT merge behavior.

The backend caches watch heart-rate readings and merges the latest fresh value
into bike sensor messages before saving and deciding.
"""

from __future__ import annotations

import json
import unittest

import backend_layer.backend_service as backend_service_module
from ai_decision_layer.decision_result import DecisionResult
from backend_layer.mqtt_receiver import MqttBackendReceiver
from backend_layer.backend_service import BackendService, parse_heart_rate_message
from common.message_schema import build_sensor_message
from config_layer.mqtt_topics import (
    HEART_RATE_TOPIC,
    MERGED_SENSORS_TOPIC,
    SENSOR_TOPIC,
)


class HeartRateMqttMergeTest(unittest.TestCase):
    """Tests for watch HR parsing, caching, expiration, and MQTT publishing."""

    def setUp(self) -> None:
        """Patch storage writes so tests can inspect saved messages."""
        self.saved_sensor_messages = []
        self.saved_decision_logs = []
        self.original_save_sensor_reading = backend_service_module.save_sensor_reading
        self.original_save_decision_log = backend_service_module.save_decision_log
        backend_service_module.save_sensor_reading = self._save_sensor_reading
        backend_service_module.save_decision_log = self._save_decision_log

    def tearDown(self) -> None:
        """Restore backend storage functions."""
        backend_service_module.save_sensor_reading = self.original_save_sensor_reading
        backend_service_module.save_decision_log = self.original_save_decision_log

    def test_parse_valid_samsung_watch_heart_rate_message(self) -> None:
        reading = parse_heart_rate_message(
            {
                "device_id": "bike_001",
                "session_id": "session_001",
                "timestamp": "2026-05-26T12:00:00",
                "heart_rate_bpm": 128,
                "source": "samsung_watch_5_pro",
            }
        )

        self.assertIsNotNone(reading)
        self.assertEqual(reading["heart_rate_bpm"], 128)
        self.assertEqual(reading["source"], "samsung_watch_5_pro")

    def test_parse_rejects_invalid_heart_rate_message(self) -> None:
        reading = parse_heart_rate_message(
            {
                "device_id": "bike_001",
                "session_id": "session_001",
                "timestamp": "2026-05-26T12:00:00",
                "heart_rate_bpm": "fast",
                "source": "samsung_watch_5_pro",
            }
        )

        self.assertIsNone(reading)

    def test_latest_heart_rate_merges_before_save_and_decision(self) -> None:
        clock = _FakeClock(100.0)
        decision_engine = _FakeDecisionEngine()
        service = BackendService(
            decision_engine=decision_engine,
            heart_rate_timeout_seconds=10.0,
            monotonic_clock=clock,
        )

        self.assertTrue(
            service.handle_heart_rate_message(
                json.dumps(
                    {
                        "device_id": "bike_001",
                        "session_id": "session_001",
                        "timestamp": "2026-05-26T12:00:00",
                        "heart_rate_bpm": 128,
                        "source": "samsung_watch_5_pro",
                    }
                )
            )
        )
        service.handle_sensor_message(json.dumps(_make_sensor_message("session_001")))

        self.assertEqual(self.saved_sensor_messages[0]["heart_rate_bpm"], 128)
        self.assertEqual(decision_engine.last_message["heart_rate_bpm"], 128)

    def test_expired_heart_rate_is_not_merged(self) -> None:
        clock = _FakeClock(100.0)
        decision_engine = _FakeDecisionEngine()
        service = BackendService(
            decision_engine=decision_engine,
            heart_rate_timeout_seconds=5.0,
            monotonic_clock=clock,
        )

        service.handle_heart_rate_message(
            json.dumps(
                {
                    "device_id": "bike_001",
                    "session_id": "session_001",
                    "timestamp": "2026-05-26T12:00:00",
                    "heart_rate_bpm": 128,
                    "source": "samsung_watch_5_pro",
                }
            )
        )
        clock.value = 106.0
        service.handle_sensor_message(json.dumps(_make_sensor_message("session_001")))

        self.assertEqual(self.saved_sensor_messages[0]["heart_rate_bpm"], 0)
        self.assertEqual(decision_engine.last_message["heart_rate_bpm"], 0)

    def test_heart_rate_is_scoped_by_device_and_session(self) -> None:
        clock = _FakeClock(100.0)
        decision_engine = _FakeDecisionEngine()
        service = BackendService(
            decision_engine=decision_engine,
            heart_rate_timeout_seconds=10.0,
            monotonic_clock=clock,
        )

        service.handle_heart_rate_message(
            json.dumps(
                {
                    "device_id": "bike_001",
                    "session_id": "session_001",
                    "timestamp": "2026-05-26T12:00:00",
                    "heart_rate_bpm": 128,
                    "source": "samsung_watch_5_pro",
                }
            )
        )
        service.handle_sensor_message(json.dumps(_make_sensor_message("session_002")))

        self.assertEqual(self.saved_sensor_messages[0]["heart_rate_bpm"], 0)

    def test_backend_receiver_routes_heart_rate_topic_to_service(self) -> None:
        service = _FakeHeartRateService()
        receiver = MqttBackendReceiver(service)

        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(HEART_RATE_TOPIC, b'{"heart_rate_bpm":128}'),
        )

        self.assertEqual(service.last_payload, b'{"heart_rate_bpm":128}')

    def test_backend_receiver_publishes_merged_sensor_with_watch_heart_rate(self) -> None:
        clock = _FakeClock(100.0)
        service = BackendService(
            decision_engine=_FakeDecisionEngine(),
            heart_rate_timeout_seconds=10.0,
            monotonic_clock=clock,
        )
        receiver = MqttBackendReceiver(service)
        receiver.publisher = _FakePublisher()

        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(
                HEART_RATE_TOPIC,
                json.dumps(
                    {
                        "device_id": "bike_001",
                        "session_id": "session_001",
                        "timestamp": "2026-05-26T12:00:00",
                        "heart_rate_bpm": 132,
                        "source": "samsung_watch_5_pro",
                    }
                ).encode("utf-8"),
            ),
        )
        receiver._on_message(
            None,
            None,
            _FakeMqttMessage(
                SENSOR_TOPIC,
                json.dumps(_make_sensor_message("session_001")).encode("utf-8"),
            ),
        )

        merged_payload = receiver.publisher.payloads[MERGED_SENSORS_TOPIC]
        self.assertEqual(merged_payload["heart_rate_bpm"], 132)
        self.assertEqual(
            set(merged_payload.keys()),
            {
                "device_id",
                "timestamp",
                "session_id",
                "workout_type",
                "speed_kmh",
                "cadence_rpm",
                "heart_rate_bpm",
                "temperature_c",
                "left_distance_m",
                "right_distance_m",
                "display_active",
                "display_message",
                "speaker_message",
                "alert_level",
                "alert_side",
                "buzzer_state",
                "led_state",
            },
        )

    def _save_sensor_reading(self, message: dict[str, object]) -> None:
        """Record sensor messages instead of writing SQLite rows."""
        self.saved_sensor_messages.append(dict(message))

    def _save_decision_log(
        self,
        sensor_message: dict[str, object],
        decision: object,
        source_topic: str | None = None,
    ) -> None:
        """Record decision log inputs instead of writing SQLite rows."""
        self.saved_decision_logs.append(
            {
                "sensor_message": dict(sensor_message),
                "decision": decision,
                "source_topic": source_topic,
            }
        )


class _FakeClock:
    """Controllable clock used to test heart-rate freshness."""

    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class _FakeDecisionEngine:
    """Decision engine fake that records the message it received."""

    def __init__(self) -> None:
        self.last_message = {}

    def analyze(self, sensor_message: dict[str, object]) -> DecisionResult:
        self.last_message = dict(sensor_message)
        return DecisionResult(
            alert_level="normal",
            alert_side="none",
            display_active=False,
            display_message="Maintain pace",
            speaker_message="",
            decision_type="normal",
            recommended_action="maintain",
            workout_type=str(sensor_message["workout_type"]),
        )


class _FakeHeartRateService:
    """Service fake used to verify receiver routing."""

    def __init__(self) -> None:
        self.last_payload = None

    def handle_heart_rate_message(self, payload: bytes) -> None:
        self.last_payload = payload


class _FakeMqttMessage:
    """Minimal paho-style MQTT message."""

    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _FakePublisher:
    """Publisher fake that records JSON payloads by topic."""

    def __init__(self) -> None:
        self.payloads = {}

    def publish_json(self, topic: str, payload: dict[str, object]) -> bool:
        self.payloads[topic] = dict(payload)
        return True


def _make_sensor_message(session_id: str) -> dict[str, object]:
    """Build a bike sensor message with heart_rate_bpm set to unavailable."""
    return build_sensor_message(
        device_id="bike_001",
        session_id=session_id,
        workout_type="speed",
        speed_kmh=20.0,
        cadence_rpm=80,
        heart_rate_bpm=0,
        temperature_c=25.0,
        left_distance_m=2.0,
        right_distance_m=2.0,
        display_active=False,
        display_message="",
        speaker_message="",
        alert_level="normal",
        alert_side="none",
    )


if __name__ == "__main__":
    unittest.main()
