"""MQTT command subscriber for bike feedback commands.

Bike runners use this to receive backend commands while optionally listening to
merged sensor messages published by the backend.
"""

from __future__ import annotations

from typing import Any

from config_layer.mqtt_topics import COMMAND_TOPIC, MERGED_SENSORS_TOPIC


class MqttCommandSubscriber:
    """Subscribe to command messages and pass them to a command handler."""

    def __init__(
        self,
        client: Any,
        command_handler: Any,
        merged_sensor_handler: Any | None = None,
    ) -> None:
        """Store the MQTT client and the handlers that should receive messages."""
        self.client = client
        self.command_handler = command_handler
        self.merged_sensor_handler = merged_sensor_handler

    def start(self) -> None:
        """Subscribe to command messages and optional merged sensor messages."""
        self.client.on_message = self._on_message
        self._subscribe(COMMAND_TOPIC, "MQTT command")
        if self.merged_sensor_handler is not None:
            self._subscribe(MERGED_SENSORS_TOPIC, "MQTT merged sensor")

    def stop(self) -> None:
        """Unsubscribe from subscribed topics."""
        self._unsubscribe(COMMAND_TOPIC, "MQTT command")
        if self.merged_sensor_handler is not None:
            self._unsubscribe(MERGED_SENSORS_TOPIC, "MQTT merged sensor")

    def _subscribe(self, topic: str, label: str) -> None:
        """Subscribe to a topic and print the broker return code."""
        result = self.client.subscribe(topic)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc == 0:
            print(f"Subscribed to {label} topic: {topic}")
        else:
            print(f"Failed to subscribe to {topic}; code: {rc}")

    def _unsubscribe(self, topic: str, label: str) -> None:
        """Unsubscribe from a topic and print the broker return code."""
        result = self.client.unsubscribe(topic)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc == 0:
            print(f"Unsubscribed from {label} topic: {topic}")
        else:
            print(f"Failed to unsubscribe from {topic}; code: {rc}")

    def _on_message(self, client: Any, userdata: object, message: Any) -> None:
        """Route command and merged-sensor messages to their handlers."""
        if message.topic == MERGED_SENSORS_TOPIC and self.merged_sensor_handler is not None:
            self.merged_sensor_handler(message.payload)
            return
        if message.topic != COMMAND_TOPIC:
            print(f"Ignored message from unexpected topic: {message.topic}")
            return

        result = self.command_handler.handle_command(message.payload)
        print(f"Command result: {result}")
