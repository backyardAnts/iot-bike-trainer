"""Convenience entry point for real Raspberry Pi/GrovePi bike mode."""

from __future__ import annotations

import argparse
import time

from config_layer.settings import DEFAULT_SAMPLE_INTERVAL_SECONDS
from config_layer.training_profiles import DEFAULT_WORKOUT_TYPE
from main_virtual_bike import run_real_mode


def run_lcd_test(lcd_debug: bool = False) -> None:
    """Run a direct LCD-only check and exit."""
    from sensor_layer.real_sensors.lcd_controller import LcdController

    lcd = LcdController(enabled=True, debug=lcd_debug)
    try:
        lcd.display("LCD TEST", "Hello Bike")
        time.sleep(5.0)
    finally:
        lcd.cleanup()


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
        default=0,
        help="placeholder heart rate value in simplified real mode",
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
    parser.add_argument(
        "--no-lcd",
        action="store_true",
        help="skip LCD initialization, display, clear, and cleanup",
    )
    parser.add_argument(
        "--lcd-debug",
        action="store_true",
        help="print LCD import and write debug information",
    )
    parser.add_argument(
        "--lcd-test",
        action="store_true",
        help="run only a direct LCD test and exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.lcd_test:
        run_lcd_test(lcd_debug=args.lcd_debug)
        raise SystemExit(0)

    run_real_mode(
        workout_type=args.workout,
        session_id=args.session_id,
        interval_seconds=args.interval,
        mqtt_enabled=args.mqtt,
        broker_host=args.broker,
        broker_port=args.mqtt_port,
        sensor_topic=args.topic,
        heart_rate_bpm=args.heart_rate,
        lcd_enabled=not args.no_lcd,
        lcd_debug=args.lcd_debug,
    )
