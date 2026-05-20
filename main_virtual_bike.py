"""Run the Phase 3 virtual bike sensor simulator."""

from __future__ import annotations

import argparse
import time
from typing import Any

from common.message_schema import message_to_json, validate_sensor_message
from config_layer.settings import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_SAMPLE_INTERVAL_SECONDS,
)
from sensor_layer.virtual_sensors.virtual_bike import VirtualBike


def run_forever(
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> None:
    """Print one JSON sensor message per sample interval until Ctrl+C."""
    bike = VirtualBike(random_seed=random_seed)
    print("Virtual bike simulator started. Press Ctrl+C to stop.")

    try:
        while True:
            message = bike.update()
            print(message_to_json(message), flush=True)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nVirtual bike simulator stopped.")


def run_mqtt_mode(
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> None:
    """Publish virtual bike readings to MQTT while also printing locally."""
    from config_layer.mqtt_topics import SENSOR_TOPIC
    from mqtt_layer.command_handler import CommandHandler
    from mqtt_layer.mqtt_client import create_mqtt_client
    from mqtt_layer.publisher import MqttPublisher
    from mqtt_layer.subscriber import MqttCommandSubscriber

    bike = VirtualBike(random_seed=random_seed)
    client: Any | None = None
    subscriber: MqttCommandSubscriber | None = None
    publisher: MqttPublisher | None = None

    try:
        client = create_mqtt_client()
        publisher = MqttPublisher(client)
        command_handler = CommandHandler(bike)
        subscriber = MqttCommandSubscriber(client, command_handler)

        client.loop_start()
        subscriber.start()

        publisher.publish_status(
            "started",
            {
                "device_id": bike.device_id,
                "session_id": bike.session_id,
            },
        )
        print("Virtual bike MQTT simulator started. Press Ctrl+C to stop.")

        while True:
            message = bike.update()
            publisher.publish_json(SENSOR_TOPIC, message)
            print(message_to_json(message), flush=True)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nVirtual bike MQTT simulator stopping.")
    finally:
        if publisher is not None:
            publisher.publish_status("stopped")
        if subscriber is not None:
            subscriber.stop()
        if client is not None:
            client.loop_stop()
            client.disconnect()
        print("Virtual bike MQTT simulator stopped.")


def run_self_test(reading_count: int = 10) -> None:
    """Run a short deterministic simulation and validate each message."""
    bike = VirtualBike(random_seed=42)
    print(f"Running virtual bike self-test for {reading_count} readings.")

    for _ in range(reading_count):
        message = bike.update()
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")
        print(message_to_json(message))

    print("Self-test passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Virtual bike simulator")
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="publish virtual bike messages to MQTT",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="print 10 readings and validate the output schema",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help="sample interval in seconds",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="optional random seed for repeatable virtual readings",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.self_test:
        run_self_test()
    elif args.mqtt:
        run_mqtt_mode(random_seed=args.seed, interval_seconds=args.interval)
    else:
        run_forever(random_seed=args.seed, interval_seconds=args.interval)
