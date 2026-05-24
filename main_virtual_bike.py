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
from config_layer.training_profiles import (
    TRAINING_PROFILES,
    WORKOUT_TYPES,
    get_training_profile,
    is_valid_workout_type,
    normalize_workout_type,
)
from sensor_layer.virtual_sensors.virtual_bike import VirtualBike


def run_forever(
    workout_type: str,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> None:
    """Print one JSON sensor message per sample interval until Ctrl+C."""
    bike = VirtualBike(workout_type=workout_type, random_seed=random_seed)
    profile = get_training_profile(bike.workout_type)
    print(f"Workout type: {profile['display_name']}")
    print("Virtual bike simulator started. Press Ctrl+C to stop.")

    try:
        while True:
            message = bike.update()
            print(message_to_json(message), flush=True)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nVirtual bike simulator stopped.")


def run_mqtt_mode(
    workout_type: str,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
) -> None:
    """Publish virtual bike readings to MQTT while also printing locally."""
    from config_layer.mqtt_topics import SENSOR_TOPIC
    from mqtt_layer.command_handler import CommandHandler
    from mqtt_layer.mqtt_client import create_mqtt_client
    from mqtt_layer.publisher import MqttPublisher
    from mqtt_layer.subscriber import MqttCommandSubscriber

    bike = VirtualBike(workout_type=workout_type, random_seed=random_seed)
    profile = get_training_profile(bike.workout_type)
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
                "workout_type": bike.workout_type,
            },
        )
        print(f"Workout type: {profile['display_name']}")
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
    print("Testing valid workout types.")
    for workout_type in WORKOUT_TYPES:
        bike = VirtualBike(workout_type=workout_type, random_seed=42)
        message = bike.update()
        if message.get("workout_type") != workout_type:
            raise RuntimeError(f"Unexpected workout type in message: {message}")
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")

    try:
        VirtualBike(workout_type="invalid")
    except ValueError:
        print("Invalid workout type rejected.")
    else:
        raise RuntimeError("Invalid workout type was accepted.")

    bike = VirtualBike(workout_type="endurance", random_seed=42)
    print(f"Running virtual bike self-test for {reading_count} readings.")

    for _ in range(reading_count):
        message = bike.update()
        if "workout_type" not in message:
            raise RuntimeError(f"Missing workout_type in sensor message: {message}")
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")
        print(message_to_json(message))

    print("Self-test passed.")


def choose_workout_type(workout_type: str | None = None) -> str:
    """Return a validated workout type from CLI input or an interactive menu."""
    if workout_type is not None:
        if is_valid_workout_type(workout_type):
            return normalize_workout_type(workout_type)
        supported = ", ".join(WORKOUT_TYPES)
        raise ValueError(
            f"Invalid workout type: {workout_type}. "
            f"Choose one of: {supported}."
        )

    while True:
        print("\nChoose workout type:")
        for index, profile_workout_type in enumerate(WORKOUT_TYPES, start=1):
            profile = TRAINING_PROFILES[profile_workout_type]
            print(f"{index}. {profile['display_name']}")

        selected = input("Enter number or workout type: ").strip()
        if selected.isdigit():
            selected_index = int(selected)
            if 1 <= selected_index <= len(WORKOUT_TYPES):
                return WORKOUT_TYPES[selected_index - 1]

        if is_valid_workout_type(selected):
            return normalize_workout_type(selected)

        supported = ", ".join(WORKOUT_TYPES)
        print(
            f"Invalid workout type. Choose 1-{len(WORKOUT_TYPES)} "
            f"or one of: {supported}."
        )


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
    parser.add_argument(
        "--workout",
        metavar="{speed,cadence,endurance,vo2_max}",
        help="workout type to simulate",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        else:
            selected_workout_type = choose_workout_type(args.workout)
            if args.mqtt:
                run_mqtt_mode(
                    workout_type=selected_workout_type,
                    random_seed=args.seed,
                    interval_seconds=args.interval,
                )
            else:
                run_forever(
                    workout_type=selected_workout_type,
                    random_seed=args.seed,
                    interval_seconds=args.interval,
                )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
