"""Convenience entry point for real Raspberry Pi/GrovePi bike mode."""

from __future__ import annotations

import argparse

from config_layer.settings import DEFAULT_SAMPLE_INTERVAL_SECONDS
from config_layer.training_profiles import DEFAULT_WORKOUT_TYPE
from main_virtual_bike import run_real_mode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real GrovePi bike sensor runner")
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="publish real sensor messages to MQTT",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help="sample interval in seconds",
    )
    parser.add_argument(
        "--workout",
        default=DEFAULT_WORKOUT_TYPE,
        metavar="{speed,cadence,endurance,vo2_max}",
        help="workout type to include in sensor messages",
    )
    parser.add_argument(
        "--session-id",
        help="optional explicit session ID for this run",
    )
    parser.add_argument(
        "--heart-rate",
        type=int,
        default=120,
        help="manual heart rate value until smartwatch support is added",
    )
    parser.add_argument(
        "--broker",
        default="localhost",
        help="MQTT broker host",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=1883,
        help="MQTT broker port",
    )
    parser.add_argument(
        "--topic",
        help="MQTT sensor topic override",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_real_mode(
        workout_type=args.workout,
        session_id=args.session_id,
        interval_seconds=args.interval,
        mqtt_enabled=args.mqtt,
        broker_host=args.broker,
        broker_port=args.mqtt_port,
        sensor_topic=args.topic,
        heart_rate_bpm=args.heart_rate,
    )
