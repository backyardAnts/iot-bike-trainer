"""Reusable MQTT client setup for the public HiveMQ broker."""

from __future__ import annotations

import uuid

import paho.mqtt.client as mqtt

from config_layer.settings import (
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_CLIENT_ID_PREFIX,
    MQTT_KEEPALIVE_SECONDS,
    MQTT_PASSWORD,
    MQTT_USERNAME,
    MQTT_USE_TLS,
)


def create_mqtt_client(
    broker_host: str | None = None,
    broker_port: int | None = None,
) -> mqtt.Client:
    """Create, configure, and connect an MQTT client."""
    client_id = f"{MQTT_CLIENT_ID_PREFIX}_{uuid.uuid4().hex[:8]}"
    host = broker_host or MQTT_BROKER_HOST
    port = int(broker_port if broker_port is not None else MQTT_BROKER_PORT)
    client = _create_paho_client(client_id)

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD or None)

    if MQTT_USE_TLS:
        client.tls_set()

    print(f"Connecting MQTT client {client_id} to {host}:{port}...")
    client.connect(host, port, MQTT_KEEPALIVE_SECONDS)
    return client


def _create_paho_client(client_id: str) -> mqtt.Client:
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )

    return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)


def _on_connect(client: mqtt.Client, userdata: object, flags: object, rc: object, *args: object) -> None:
    reason = getattr(rc, "value", rc)
    if reason == 0:
        print("MQTT connected successfully.")
    else:
        print(f"MQTT connection failed with code: {reason}")


def _on_disconnect(client: mqtt.Client, userdata: object, *args: object) -> None:
    reason = _extract_disconnect_reason(args)
    if reason in (0, None):
        print("MQTT disconnected cleanly.")
    else:
        print(f"MQTT disconnected with code: {reason}")


def _on_message(client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
    payload = message.payload.decode("utf-8", errors="replace")
    print(f"MQTT message received on {message.topic}: {payload}")


def _extract_disconnect_reason(args: tuple[object, ...]) -> object:
    if not args:
        return None

    reason = args[-2] if len(args) >= 2 else args[-1]
    return getattr(reason, "value", reason)
