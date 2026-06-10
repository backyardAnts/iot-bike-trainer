"""Convenience entry point for real Raspberry Pi/GrovePi bike mode.

This file keeps the real-hardware command line small and passes the actual
work to ``run_real_mode`` in ``main_virtual_bike.py``.
"""

from __future__ import annotations

import argparse
import time

from config_layer.settings import (
    DEFAULT_SAMPLE_INTERVAL_SECONDS,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
)
from config_layer.training_profiles import DEFAULT_WORKOUT_TYPE
from main_virtual_bike import run_real_mode


def run_lcd_test(lcd_debug: bool = False) -> None:
    """Run a direct LCD-only check and exit."""
    from sensor_layer.real_sensors.lcd_controller import LcdController

    lcd = LcdController(enabled=True, debug=lcd_debug)
    try:
        # This is only a hardware smoke test, so it writes one fixed message.
        lcd.display("LCD TEST", "Hello Bike")
        time.sleep(5.0)
    finally:
        # Always release the LCD even if the sleep is interrupted.
        lcd.cleanup()


def parse_args() -> argparse.Namespace:
    """Read options for the Raspberry Pi runner."""
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
        help=f"optional MQTT broker host override (default: {MQTT_BROKER_HOST})",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        help=f"optional MQTT broker port override (default: {MQTT_BROKER_PORT})",
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
    parser.add_argument(
        "--wheel-diameter-cm",
        type=float,
        default=70.0,
        help="wheel diameter in centimeters for speed calculation",
    )
    parser.add_argument(
        "--speed-magnets-per-rotation",
        type=int,
        default=1,
        help="speed Hall magnet passes per wheel rotation",
    )
    parser.add_argument(
        "--cadence-magnets-per-rotation",
        type=int,
        default=1,
        help="cadence Hall magnet passes per crank rotation",
    )
    parser.add_argument(
        "--enable-hall",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-hall",
        action="store_true",
        help="disable D3/D4 Hall speed and cadence sensors",
    )
    parser.add_argument(
        "--hall-debug",
        action="store_true",
        help="print raw D3/D4 Hall values and counted events",
    )
    parser.add_argument(
        "--temperature-sensor-type",
        type=int,
        default=0,
        help="Grove DHT sensor type for temperature/humidity sensor on D2",
    )
    parser.add_argument(
        "--no-temperature",
        action="store_true",
        help="disable D2 temperature/humidity sensor",
    )
    parser.add_argument(
        "--temperature-debug",
        action="store_true",
        help="print raw D2 temperature/humidity readings and fallback information",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.lcd_test:
        # LCD test mode should not start the bike loop.
        run_lcd_test(lcd_debug=args.lcd_debug)
        raise SystemExit(0)

    # Most flags are passed through because run_real_mode is shared by tests too.
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
        wheel_diameter_cm=args.wheel_diameter_cm,
        speed_magnets_per_rotation=args.speed_magnets_per_rotation,
        cadence_magnets_per_rotation=args.cadence_magnets_per_rotation,
        enable_hall=not args.no_hall,
        hall_debug=args.hall_debug,
        enable_temperature=not args.no_temperature,
        temperature_sensor_type=args.temperature_sensor_type,
        temperature_debug=args.temperature_debug,
    )
