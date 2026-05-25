"""Production Grove RGB LCD controller."""

from __future__ import annotations

import sys
from typing import Any, Callable, Optional, Tuple


GROVE_LCD_PATHS = (
    "/home/pi/Dexter/GrovePi/Software/Python",
    "/home/pi/Dexter/GrovePi/Software/Python/grove_rgb_lcd",
    "/home/pi/Dexter/GrovePi/Software/Python/grovepi",
)

LCD_IMPORT_ERROR = None

try:
    from grove_rgb_lcd import *
except ImportError as first_import_error:
    LCD_IMPORT_ERROR = first_import_error
    for grove_lcd_path in GROVE_LCD_PATHS:
        if grove_lcd_path not in sys.path:
            sys.path.append(grove_lcd_path)
    try:
        from grove_rgb_lcd import *
        LCD_IMPORT_ERROR = None
    except ImportError as second_import_error:
        LCD_IMPORT_ERROR = second_import_error


class LcdController(object):
    """Write short two-line messages to the Grove I2C LCD."""

    def __init__(self, enabled: bool = True, debug: bool = False) -> None:
        self._set_text = None  # type: Optional[Callable[..., Any]]
        self._set_color = None  # type: Optional[Callable[..., Any]]
        self._color_function_name = ""  # type: str
        self.available = False
        self.debug = bool(debug)
        self._last_error = ""
        self._color_error_printed = False
        self._last_message = None  # type: Optional[str]

        if not enabled:
            return

        self._set_text, self._set_color, self._color_function_name = (
            self._get_lcd_functions()
        )
        self.available = callable(self._set_text)

        if self.debug:
            print("LCD debug: import succeeded={}".format(self.available))
            print("LCD debug: setText={}".format(self._set_text))
            print(
                "LCD debug: color function {}={}".format(
                    self._color_function_name or "none",
                    self._set_color,
                )
            )

        if not self.available:
            self._disable_with_warning(
                "LCD disabled: Grove LCD import failed: {}".format(LCD_IMPORT_ERROR)
            )

    def display(self, line1: str, line2: str = "") -> None:
        """Display up to two short LCD lines."""
        if not self.available or self._set_text is None:
            return

        line1 = self._short_line(line1)
        line2 = self._short_line(line2)
        message = "{}\n{}".format(line1, line2)
        if message == self._last_message:
            return

        if self._set_color is not None:
            try:
                if self.debug:
                    print(
                        "LCD debug: calling {}(0, 128, 64)".format(
                            self._color_function_name
                        )
                    )
                self._set_color(0, 128, 64)
            except Exception as exc:
                self._warn_color_once("LCD color error: {}".format(exc))

        try:
            if self.debug:
                print("LCD debug: calling setText({!r})".format(message))
            self._set_text(message)
            self._last_message = message
            print("LCD update: {} | {}".format(line1, line2))
        except Exception as exc:
            self._disable_with_warning("LCD text error; LCD disabled: {}".format(exc))

    def clear(self) -> None:
        """Clear LCD text if available."""
        if not self.available or self._set_text is None:
            return

        try:
            if self.debug:
                print("LCD debug: calling setText('')")
            self._set_text("")
            self._last_message = None
        except Exception as exc:
            self._disable_with_warning("LCD clear error; LCD disabled: {}".format(exc))

    def cleanup(self) -> None:
        """Clear the LCD before exiting."""
        self.clear()

    def _get_lcd_functions(
        self,
    ) -> Tuple[
        Optional[Callable[..., Any]],
        Optional[Callable[..., Any]],
        str,
    ]:
        set_text = globals().get("setText")
        set_rgb = globals().get("setRGB")
        set_color = globals().get("setColor")

        if callable(set_rgb):
            return set_text, set_rgb, "setRGB"
        if callable(set_color):
            return set_text, set_color, "setColor"
        return set_text, None, ""

    def _short_line(self, value: str) -> str:
        return str(value)[:16]

    def _disable_with_warning(self, message: str) -> None:
        self.available = False
        self._set_text = None
        self._set_color = None
        self._last_message = None
        self._warn_once(message)

    def _warn_color_once(self, message: str) -> None:
        if self._color_error_printed:
            return
        self._color_error_printed = True
        print(message)

    def _warn_once(self, message: str) -> None:
        if self._last_error:
            return
        self._last_error = message
        print(message)
