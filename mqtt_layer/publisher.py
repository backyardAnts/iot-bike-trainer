"""Publishing helpers for MQTT messages."""

from __future__ import annotations

import json
from typing import Any

from common.time_utils import get_current_timestamp
from config_layer.mqtt_topics import STATUS_TOPIC


class MqttPublisher:
    """Publish JSON, text, and status messages through an MQTT client."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def publish_json(
        self,
        topic: str,
        payload: dict[str, Any],
        retain: bool = False,
    ) -> bool:
        """Publish a dictionary as JSON."""
        try:
            payload_text = json.dumps(payload, separators=(",", ":"))
            return self._publish(topic, payload_text, retain=retain)
        except Exception as exc:
            print(f"Failed to publish JSON to {topic}: {exc}")
            return False

    def publish_text(self, topic: str, payload: str, retain: bool = False) -> bool:
        """Publish plain text."""
        try:
            return self._publish(topic, payload, retain=retain)
        except Exception as exc:
            print(f"Failed to publish text to {topic}: {exc}")
            return False

    def publish_status(self, status: str, extra: dict[str, Any] | None = None) -> bool:
        """Publish a status message to the configured status topic."""
        payload = {
            "status": status,
            "timestamp": get_current_timestamp(),
        }
        if extra:
            payload.update(extra)

        return self.publish_json(STATUS_TOPIC, payload)

    def _publish(self, topic: str, payload: str, retain: bool = False) -> bool:
        if retain:
            result = self.client.publish(topic, payload, retain=True)
        else:
            result = self.client.publish(topic, payload)
        rc = getattr(result, "rc", 0)
        if rc != 0:
            print(f"MQTT publish to {topic} returned code {rc}.")
            return False

        print(f"Published MQTT message to {topic}.")
        return True
