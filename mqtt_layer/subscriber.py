"""MQTT command subscriber for bike feedback commands."""

from __future__ import annotations

from typing import Any

from config_layer.mqtt_topics import COMMAND_TOPIC


class MqttCommandSubscriber:
    """Subscribe to command messages and pass them to a command handler."""

    def __init__(self, client: Any, command_handler: Any) -> None:
        self.client = client
        self.command_handler = command_handler

    def start(self) -> None:
        """Subscribe to the command topic."""
        self.client.on_message = self._on_message
        result = self.client.subscribe(COMMAND_TOPIC)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc == 0:
            print(f"Subscribed to MQTT command topic: {COMMAND_TOPIC}")
        else:
            print(f"Failed to subscribe to {COMMAND_TOPIC}; code: {rc}")

    def stop(self) -> None:
        """Unsubscribe from the command topic."""
        result = self.client.unsubscribe(COMMAND_TOPIC)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc == 0:
            print(f"Unsubscribed from MQTT command topic: {COMMAND_TOPIC}")
        else:
            print(f"Failed to unsubscribe from {COMMAND_TOPIC}; code: {rc}")

    def _on_message(self, client: Any, userdata: object, message: Any) -> None:
        result = self.command_handler.handle_command(message.payload)
        print(f"Command result: {result}")
