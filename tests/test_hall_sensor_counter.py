"""Tests for production Hall speed/cadence interval smoothing.

These tests replace GrovePi and time with fakes so pulse timing can be checked
without Raspberry Pi hardware.
"""

from __future__ import annotations

import unittest
from unittest import mock

from sensor_layer.real_sensors import hall_sensor_counter as hall_module


class HallSensorCounterTest(unittest.TestCase):
    """Unit tests for debouncing, timeout, and missed-pulse smoothing."""

    def setUp(self) -> None:
        """Patch GrovePi and monotonic time with deterministic fakes."""
        self.fake_grovepi = _FakeGrovePi()
        self.clock = _FakeClock()
        self.load_patch = mock.patch.object(
            hall_module,
            "load_grovepi",
            return_value=self.fake_grovepi,
        )
        self.time_patch = mock.patch.object(
            hall_module.time,
            "monotonic",
            self.clock.monotonic,
        )
        self.load_patch.start()
        self.time_patch.start()

    def tearDown(self) -> None:
        """Restore patched imports and time functions."""
        self.time_patch.stop()
        self.load_patch.stop()

    def test_defaults_match_fast_production_polling_settings(self) -> None:
        counter = self._make_counter()

        self.assertEqual(counter.poll_interval_seconds, 0.001)
        self.assertEqual(counter.debounce_seconds, 0.02)
        self.assertEqual(counter.timeout_seconds, 3.0)
        self.assertEqual(counter.average_window, 5)
        self.assertEqual(counter.magnets_per_rotation, 1)

    def test_rolling_average_corrects_one_suspicious_long_interval(self) -> None:
        counter = self._make_counter()
        self._prime_normal_state(counter)

        self._pulse(counter, 0.100)
        self._pulse(counter, 0.440)
        self._pulse(counter, 0.780)
        self._pulse(counter, 1.120)
        self._pulse(counter, 1.789)

        measurement = counter.get_measurement()

        self.assertEqual(measurement["event_count"], 5)
        self.assertAlmostEqual(measurement["period_seconds"], 0.3345, places=3)
        self.assertGreater(measurement["events_per_second"], 2.8)
        self.assertLess(measurement["events_per_second"], 3.1)

    def test_repeated_long_intervals_adapt_as_real_slowdown(self) -> None:
        counter = self._make_counter()
        self._prime_normal_state(counter)

        self._pulse(counter, 0.100)
        self._pulse(counter, 0.440)
        self._pulse(counter, 0.780)
        self._pulse(counter, 1.120)
        self._pulse(counter, 1.790)
        self._pulse(counter, 2.460)

        measurement = counter.get_measurement()

        self.assertAlmostEqual(measurement["average_period_seconds"], 0.67, places=2)
        self.assertAlmostEqual(measurement["events_per_second"], 1.49, places=2)

    def test_speed_returns_zero_only_after_timeout(self) -> None:
        counter = self._make_counter()
        self._prime_normal_state(counter)

        self._pulse(counter, 0.100)
        self._pulse(counter, 0.440)
        self.clock.now = 3.300
        before_timeout = counter.get_measurement()
        self.clock.now = 3.500
        after_timeout = counter.get_measurement()

        self.assertGreater(before_timeout["events_per_second"], 0.0)
        self.assertEqual(after_timeout["events_per_second"], 0.0)
        self.assertEqual(after_timeout["rotations_per_second"], 0.0)

    def test_magnets_per_rotation_scales_rotations(self) -> None:
        counter = self._make_counter(magnets_per_rotation=2)
        self._prime_normal_state(counter)

        self._pulse(counter, 0.100)
        self._pulse(counter, 0.350)

        measurement = counter.get_measurement()

        self.assertAlmostEqual(measurement["events_per_second"], 4.0, places=2)
        self.assertAlmostEqual(measurement["rotations_per_second"], 2.0, places=2)

    def _make_counter(self, magnets_per_rotation: int = 1) -> hall_module.HallSensorCounter:
        """Create a counter wired to the fake GrovePi object."""
        return hall_module.HallSensorCounter(
            port=3,
            label="Speed",
            magnets_per_rotation=magnets_per_rotation,
        )

    def _prime_normal_state(self, counter: hall_module.HallSensorCounter) -> None:
        """Set the initial non-magnet state before pulses are simulated."""
        self._set_state(counter, 0.000, 1)

    def _pulse(
        self,
        counter: hall_module.HallSensorCounter,
        pulse_time: float,
    ) -> None:
        """Simulate one falling edge into the magnet-detected state."""
        self._set_state(counter, pulse_time - 0.001, 1)
        self._set_state(counter, pulse_time, 0)

    def _set_state(
        self,
        counter: hall_module.HallSensorCounter,
        now: float,
        state: int,
    ) -> None:
        """Move fake time and fake digital input before polling once."""
        self.clock.now = now
        self.fake_grovepi.state = state
        counter.poll_once()


class _FakeClock(object):
    """Controllable replacement for time.monotonic."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


class _FakeGrovePi(object):
    """Tiny GrovePi fake with one digital input state."""

    def __init__(self) -> None:
        self.state = 1
        self.modes = {}

    def pinMode(self, port: int, mode: str) -> None:
        self.modes[int(port)] = str(mode)

    def digitalRead(self, port: int) -> int:
        return self.state


if __name__ == "__main__":
    unittest.main()
