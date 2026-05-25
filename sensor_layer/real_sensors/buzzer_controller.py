"""Production GrovePi buzzer controller."""

from __future__ import annotations

import time
from typing import Any

from sensor_layer.real_sensors.grovepi_imports import get_grovepi_error, load_grovepi


class BuzzerController(object):
    """Control a Grove buzzer connected to a digital port."""

    def __init__(self, port: int = 7) -> None:
        self.port = int(port)
        self.enabled = False
        self.grovepi = load_grovepi()
        self._last_error = ""

        if self.grovepi is None:
            self._warn_once(
                "Buzzer disabled: GrovePi import failed: {}".format(
                    get_grovepi_error()
                )
            )
            return

        try:
            self.grovepi.pinMode(self.port, "OUTPUT")
            self.grovepi.digitalWrite(self.port, 0)
        except Exception as exc:
            self._warn_once("Buzzer D{} setup failed: {}".format(self.port, exc))

    def on(self) -> None:
        """Turn the buzzer on."""
        self.set_state(True)

    def off(self) -> None:
        """Turn the buzzer off."""
        self.set_state(False)

    def set_state(self, enabled: bool, force: bool = False) -> None:
        """Set the buzzer state."""
        next_enabled = bool(enabled)
        if self.enabled == next_enabled and not force:
            return

        self.enabled = next_enabled
        if self.grovepi is None:
            return

        try:
            self.grovepi.digitalWrite(self.port, 1 if self.enabled else 0)
        except Exception as exc:
            self._warn_once("Buzzer D{} write failed: {}".format(self.port, exc))

    def beep(self, duration: float = 0.2) -> None:
        """Beep once for the requested duration."""
        self.on()
        time.sleep(float(duration))
        self.off()

    def cleanup(self) -> None:
        """Always turn the buzzer off before exiting."""
        self.set_state(False, force=True)

    def _warn_once(self, message: str) -> None:
        if message == self._last_error:
            return
        self._last_error = message
        print(message)
