"""MQTT receiver for the backend SQLite service.

This class owns MQTT subscriptions and publishing. BackendService owns the
actual parsing, storage, and decision work.
"""

from __future__ import annotations

from typing import Any

from config_layer.mqtt_topics import (
    COMMAND_TOPIC,
    HEART_RATE_TOPIC,
    MERGED_SENSORS_TOPIC,
    SENSOR_TOPIC,
    SESSION_TOPIC,
    STATUS_TOPIC,
)
from mqtt_layer.publisher import MqttPublisher


class MqttBackendReceiver:
    """Subscribe to backend topics and route payloads to BackendService."""

    def __init__(self, backend_service: Any) -> None:
        """Store the service that will handle incoming MQTT payloads."""
        self.backend_service = backend_service
        self.client: Any | None = None
        self.publisher: MqttPublisher | None = None

    def start(self) -> None:
        """Connect to MQTT, subscribe to backend topics, and start the loop."""
        from mqtt_layer.mqtt_client import create_mqtt_client

        self.client = create_mqtt_client()
        self.publisher = MqttPublisher(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        # The paho loop runs callbacks on its own thread.
        self.client.loop_start()
        print("Backend MQTT receiver started.")

    def stop(self) -> None:
        """Unsubscribe and disconnect cleanly."""
        if self.client is None:
            return

        for topic in (SENSOR_TOPIC, STATUS_TOPIC, COMMAND_TOPIC, HEART_RATE_TOPIC):
            self.client.unsubscribe(topic)

        self.client.loop_stop()
        self.client.disconnect()
        self.client = None
        self.publisher = None

    def _subscribe(self, topic: str) -> None:
        """Subscribe to one topic and log the broker return code."""
        if self.client is None:
            return

        result = self.client.subscribe(topic)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc == 0:
            print(f"Subscribed to {topic}")
        else:
            print(f"Failed to subscribe to {topic}; code: {rc}")

    def _on_connect(
        self,
        client: Any,
        userdata: object,
        flags: object,
        rc: object,
        *args: object,
    ) -> None:
        """Subscribe to all backend topics after the broker accepts the connection."""
        reason = getattr(rc, "value", rc)
        if reason != 0:
            print(f"Backend MQTT connection failed with code: {reason}")
            return

        print("Backend connected to MQTT broker.")
        for topic in (SENSOR_TOPIC, STATUS_TOPIC, COMMAND_TOPIC, HEART_RATE_TOPIC):
            self._subscribe(topic)

    def _on_message(self, client: Any, userdata: object, message: Any) -> None:
        """Route one MQTT message based on its topic."""
        if message.topic == SENSOR_TOPIC:
            feedback_command = self.backend_service.handle_sensor_message(
                message.payload,
                source_topic=message.topic,
            )
            self._publish_merged_sensor_message(
                self.backend_service.get_latest_merged_sensor_message()
            )
            # Feedback goes back to the same command topic the bike listens to.
            if feedback_command is not None:
                self._publish_feedback_command(feedback_command)
            return

        if message.topic == HEART_RATE_TOPIC:
            self.backend_service.handle_heart_rate_message(message.payload)
            return

        if message.topic == STATUS_TOPIC:
            session_payload = self.backend_service.handle_status_message(
                message.topic,
                message.payload,
            )
            if session_payload is not None:
                self._publish_session_message(session_payload)
            return

        if message.topic == COMMAND_TOPIC:
            self.backend_service.handle_command_message(message.payload)
            return

        print(f"Ignored message from unexpected topic: {message.topic}")

    def _publish_feedback_command(self, feedback_command: dict[str, Any]) -> None:
        """Publish a feedback command generated from a sensor decision."""
        if self.publisher is None:
            print("Could not publish feedback command: MQTT publisher is not ready.")
            return

        if self.publisher.publish_json(COMMAND_TOPIC, feedback_command):
            print(f"Published feedback command to {COMMAND_TOPIC}")

    def _publish_merged_sensor_message(
        self,
        merged_sensor_message: dict[str, Any] | None,
    ) -> None:
        """Publish the sensor message after watch heart-rate merging."""
        if merged_sensor_message is None:
            return
        if self.publisher is None:
            print("Could not publish merged sensor message: MQTT publisher is not ready.")
            return

        if self.publisher.publish_json(MERGED_SENSORS_TOPIC, merged_sensor_message):
            print(f"Published merged sensor message to {MERGED_SENSORS_TOPIC}")

    def _publish_session_message(self, session_payload: dict[str, Any]) -> None:
        """Publish retained active/stopped session state for dashboards."""
        if self.publisher is None:
            print("Could not publish session message: MQTT publisher is not ready.")
            return

        if self.publisher.publish_json(SESSION_TOPIC, session_payload, retain=True):
            session_status = str(session_payload.get("status", ""))
            print(f"Published {session_status} session to {SESSION_TOPIC}")
