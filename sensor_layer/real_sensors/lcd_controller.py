"""Production Grove RGB LCD controller."""

from __future__ import annotations

from typing import Any, Callable, Optional

from sensor_layer.real_sensors.grovepi_imports import (
    get_lcd_error,
    load_lcd_functions,
)


class LcdController(object):
    """Write short two-line messages to the Grove I2C LCD."""

    def __init__(self, enabled: bool = True) -> None:
        self._set_text = None  # type: Optional[Callable[..., Any]]
        self._set_rgb = None  # type: Optional[Callable[..., Any]]
        self.available = False
        self._last_error = ""
        self._last_message = None  # type: Optional[str]

        if not enabled:
            return

        set_text, set_rgb = load_lcd_functions()
        self._set_text = set_text  # type: Optional[Callable[..., Any]]
        self._set_rgb = set_rgb  # type: Optional[Callable[..., Any]]
        self.available = callable(set_text) and callable(set_rgb)

        if not self.available:
            self._disable_with_warning(
                "LCD disabled: Grove LCD import failed: {}".format(get_lcd_error())
            )

    def display(self, line1: str, line2: str = "") -> None:
        """Display up to two short LCD lines."""
        if not self.available or self._set_text is None or self._set_rgb is None:
            return

        line1 = self._short_line(line1)
        line2 = self._short_line(line2)
        message = "{}\n{}".format(line1, line2)
        if message == self._last_message:
            return

        try:
            self._set_rgb(0, 128, 64)
        except Exception as exc:
            self._disable_with_warning("LCD color failed; LCD disabled: {}".format(exc))
            return

        try:
            self._set_text(message)
            self._last_message = message
        except Exception as exc:
            self._disable_with_warning("LCD text failed; LCD disabled: {}".format(exc))

    def clear(self) -> None:
        """Clear LCD text if available."""
        if not self.available or self._set_text is None:
            return

        try:
            self._set_text("")
            self._last_message = None
        except Exception as exc:
            self._disable_with_warning("LCD clear failed; LCD disabled: {}".format(exc))

    def cleanup(self) -> None:
        """Clear the LCD before exiting."""
        self.clear()

    def _short_line(self, value: str) -> str:
        return str(value)[:16]

    def _disable_with_warning(self, message: str) -> None:
        self.available = False
        self._set_text = None
        self._set_rgb = None
        self._last_message = None
        self._warn_once(message)

    def _warn_once(self, message: str) -> None:
        if self._last_error:
            return
        self._last_error = message
        print(message)
