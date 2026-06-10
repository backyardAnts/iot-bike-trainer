"""Tests for real mode MQTT wiring without opening a network connection.

The real-mode runner imports MQTT and RealBike lazily, so these tests replace
those modules with fakes and verify the shared MQTT client is called correctly.
"""

from __future__ import annotations

import sys
import types
import unittest

import main_virtual_bike
from common.message_schema import build_sensor_message


class RealMqttUsesSharedLayerTest(unittest.TestCase):
    """Integration-style tests for real-mode MQTT setup arguments."""

    def test_real_mode_uses_shared_mqtt_client_defaults(self) -> None:
        """Default real MQTT mode should use the configured broker values."""
        calls = []
        fake_mqtt_module = types.ModuleType("mqtt_layer.mqtt_client")
        fake_mqtt_module.create_mqtt_client = (
            lambda broker_host=None, broker_port=None: _record_client_call(
                calls,
                broker_host,
                broker_port,
            )
        )

        fake_real_module = types.ModuleType("sensor_layer.real_sensors.real_bike")
        fake_real_module.RealBike = _FakeRealBike

        original_mqtt_module = sys.modules.get("mqtt_layer.mqtt_client")
        original_real_module = sys.modules.get("sensor_layer.real_sensors.real_bike")
        sys.modules["mqtt_layer.mqtt_client"] = fake_mqtt_module
        sys.modules["sensor_layer.real_sensors.real_bike"] = fake_real_module

        try:
            # _FakeRealBike raises KeyboardInterrupt during idle wait to exit the loop.
            main_virtual_bike.run_real_mode(
                workout_type="speed",
                interval_seconds=0,
                mqtt_enabled=True,
                lcd_enabled=False,
            )
        finally:
            _restore_module("mqtt_layer.mqtt_client", original_mqtt_module)
            _restore_module("sensor_layer.real_sensors.real_bike", original_real_module)

        self.assertEqual(calls, [(None, None)])

    def test_real_mode_passes_optional_mqtt_override_to_shared_client(self) -> None:
        """Explicit broker overrides should be passed to create_mqtt_client."""
        calls = []
        fake_mqtt_module = types.ModuleType("mqtt_layer.mqtt_client")
        fake_mqtt_module.create_mqtt_client = (
            lambda broker_host=None, broker_port=None: _record_client_call(
                calls,
                broker_host,
                broker_port,
            )
        )

        fake_real_module = types.ModuleType("sensor_layer.real_sensors.real_bike")
        fake_real_module.RealBike = _FakeRealBike

        original_mqtt_module = sys.modules.get("mqtt_layer.mqtt_client")
        original_real_module = sys.modules.get("sensor_layer.real_sensors.real_bike")
        sys.modules["mqtt_layer.mqtt_client"] = fake_mqtt_module
        sys.modules["sensor_layer.real_sensors.real_bike"] = fake_real_module

        try:
            main_virtual_bike.run_real_mode(
                workout_type="speed",
                interval_seconds=0,
                mqtt_enabled=True,
                broker_host="example.test",
                broker_port=1884,
                lcd_enabled=False,
            )
        finally:
            _restore_module("mqtt_layer.mqtt_client", original_mqtt_module)
            _restore_module("sensor_layer.real_sensors.real_bike", original_real_module)

        self.assertEqual(calls, [("example.test", 1884)])


class _FakeRealBike:
    """RealBike fake that lets run_real_mode start without hardware."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.device_id = "bike_001"
        self.session_id = "session_real_test"
        self.workout_type = "speed"
        self.command_feedback_enabled = kwargs.get("command_feedback_enabled", False)

    def set_command_feedback_enabled(self, enabled: bool) -> None:
        self.command_feedback_enabled = bool(enabled)

    def show_startup_lcd_message(self) -> None:
        return None

    def update(self) -> dict[str, object]:
        return build_sensor_message(
            device_id=self.device_id,
            session_id=self.session_id,
            workout_type=self.workout_type,
            speed_kmh=12.0,
            cadence_rpm=70,
            heart_rate_bpm=0,
            temperature_c=25.0,
            left_distance_m=1.0,
            right_distance_m=1.0,
            display_active=False,
            display_message="SAFE",
            speaker_message="",
            alert_level="normal",
            alert_side="none",
            buzzer_state=False,
            led_state=False,
        )

    def get_latest_status_line(self) -> str:
        return ""

    def wait_between_updates(self, duration_seconds: float) -> None:
        raise KeyboardInterrupt

    def cleanup(self) -> None:
        return None


class _FakeClient:
    """MQTT client fake used by the publisher/subscriber wrappers."""

    def loop_start(self) -> None:
        return None

    def loop_stop(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def publish(self, topic: str, payload: str) -> object:
        return types.SimpleNamespace(rc=0)

    def subscribe(self, topic: str) -> tuple[int, int]:
        return (0, 1)

    def unsubscribe(self, topic: str) -> tuple[int, int]:
        return (0, 1)


def _record_client_call(
    calls: list[tuple[str | None, int | None]],
    broker_host: str | None,
    broker_port: int | None,
) -> _FakeClient:
    """Record the broker arguments and return a fake MQTT client."""
    calls.append((broker_host, broker_port))
    return _FakeClient()


def _restore_module(name: str, original_module: object | None) -> None:
    """Put sys.modules back the way the test found it."""
    if original_module is None:
        sys.modules.pop(name, None)
        return
    sys.modules[name] = original_module


if __name__ == "__main__":
    unittest.main()
