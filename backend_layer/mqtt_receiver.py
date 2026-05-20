"""MQTT receiver for the backend SQLite service."""

from __future__ import annotations

from typing import Any

from config_layer.mqtt_topics import COMMAND_TOPIC, SENSOR_TOPIC, STATUS_TOPIC
from mqtt_layer.mqtt_client import create_mqtt_client


class MqttBackendReceiver:
    """Subscribe to backend topics and route payloads to BackendService."""

    def __init__(self, backend_service: Any) -> None:
        self.backend_service = backend_service
        self.client: Any | None = None

    def start(self) -> None:
        """Connect to MQTT, subscribe to backend topics, and start the loop."""
        self.client = create_mqtt_client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.loop_start()
        print("Backend MQTT receiver started.")

    def stop(self) -> None:
        """Unsubscribe and disconnect cleanly."""
        if self.client is None:
            return

        for topic in (SENSOR_TOPIC, STATUS_TOPIC, COMMAND_TOPIC):
            self.client.unsubscribe(topic)

        self.client.loop_stop()
        self.client.disconnect()
        self.client = None

    def _subscribe(self, topic: str) -> None:
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
        reason = getattr(rc, "value", rc)
        if reason != 0:
            print(f"Backend MQTT connection failed with code: {reason}")
            return

        print("Backend connected to MQTT broker.")
        for topic in (SENSOR_TOPIC, STATUS_TOPIC, COMMAND_TOPIC):
            self._subscribe(topic)

    def _on_message(self, client: Any, userdata: object, message: Any) -> None:
        if message.topic == SENSOR_TOPIC:
            self.backend_service.handle_sensor_message(message.payload)
            return

        if message.topic == STATUS_TOPIC:
            self.backend_service.handle_status_message(message.topic, message.payload)
            return

        if message.topic == COMMAND_TOPIC:
            self.backend_service.handle_command_message(message.payload)
            return

        print(f"Ignored message from unexpected topic: {message.topic}")
