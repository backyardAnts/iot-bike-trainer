"""Composite virtual bike that exposes one JSON-ready sensor reading."""

from __future__ import annotations

import random
from typing import Any

from common.message_schema import build_sensor_message
from config_layer import settings
from sensor_layer.virtual_sensors.cadence_sensor import VirtualCadenceSensor
from sensor_layer.virtual_sensors.heart_rate_sensor import VirtualHeartRateSensor
from sensor_layer.virtual_sensors.proximity_sensor import VirtualProximitySensor
from sensor_layer.virtual_sensors.speed_sensor import VirtualSpeedSensor
from sensor_layer.virtual_sensors.temperature_sensor import VirtualTemperatureSensor


class VirtualBike:
    """Combine all Phase 3 virtual sensors behind one update API."""

    def __init__(
        self,
        device_id: str = settings.DEVICE_ID,
        session_id: str = settings.DEFAULT_SESSION_ID,
        random_seed: int | None = settings.DEFAULT_RANDOM_SEED,
    ) -> None:
        self.device_id = device_id
        self.session_id = session_id
        self.buzzer_state = False

        master_rng = random.Random(random_seed)
        self.speed_sensor = VirtualSpeedSensor(rng=_make_child_rng(master_rng))
        self.cadence_sensor = VirtualCadenceSensor(rng=_make_child_rng(master_rng))
        self.heart_rate_sensor = VirtualHeartRateSensor(rng=_make_child_rng(master_rng))
        self.temperature_sensor = VirtualTemperatureSensor(rng=_make_child_rng(master_rng))
        self.left_proximity_sensor = VirtualProximitySensor(
            side="left",
            rng=_make_child_rng(master_rng),
        )
        self.right_proximity_sensor = VirtualProximitySensor(
            side="right",
            rng=_make_child_rng(master_rng),
        )

        self._latest_message: dict[str, Any] | None = None

    def update(self) -> dict[str, Any]:
        """Update all sensors in dependency order and return the message."""
        speed_kmh = self.speed_sensor.update()
        riding_mode = self.speed_sensor.riding_mode
        cadence_rpm = self.cadence_sensor.update(speed_kmh, riding_mode)
        heart_rate_bpm = self.heart_rate_sensor.update(
            speed_kmh,
            cadence_rpm,
            riding_mode,
        )
        temperature_c = self.temperature_sensor.update()
        left_distance_m = self.left_proximity_sensor.update()
        right_distance_m = self.right_proximity_sensor.update()

        self._latest_message = build_sensor_message(
            device_id=self.device_id,
            session_id=self.session_id,
            speed_kmh=speed_kmh,
            cadence_rpm=cadence_rpm,
            heart_rate_bpm=heart_rate_bpm,
            temperature_c=temperature_c,
            left_distance_m=left_distance_m,
            right_distance_m=right_distance_m,
            buzzer_state=self.buzzer_state,
        )
        return self._latest_message

    def get_current_reading(self) -> dict[str, Any]:
        """Return the latest message, updating once if no reading exists yet."""
        if self._latest_message is None:
            return self.update()
        return self._latest_message

    def set_buzzer_state(self, state: bool) -> None:
        """Set the virtual buzzer state without applying any AI rule."""
        self.buzzer_state = bool(state)

    def turn_buzzer_on(self) -> None:
        """Turn the virtual buzzer on."""
        self.set_buzzer_state(True)

    def turn_buzzer_off(self) -> None:
        """Turn the virtual buzzer off."""
        self.set_buzzer_state(False)


def _make_child_rng(master_rng: random.Random) -> random.Random:
    return random.Random(master_rng.randrange(0, 2**32))

