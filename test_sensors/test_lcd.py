"""Simple Grove RGB LCD test through I2C.

The full bike uses short two-line LCD messages, so this script cycles through
the same kind of display content and colors.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Callable, Optional, Tuple


DEFAULT_INTERVAL_SECONDS = 2.0
GROVE_LCD_PATHS = (
    "/home/pi/Dexter/GrovePi/Software/Python",
    "/home/pi/Dexter/GrovePi/Software/Python/grove_rgb_lcd",
    "/home/pi/Dexter/GrovePi/Software/Python/grovepi",
)

LCD_IMPORT_ERROR = None

try:
    from grove_rgb_lcd import *
except ImportError as first_import_error:
    # Retry after adding common Grove LCD paths from Raspberry Pi installs.
    LCD_IMPORT_ERROR = first_import_error
    for grove_lcd_path in GROVE_LCD_PATHS:
        if grove_lcd_path not in sys.path:
            sys.path.append(grove_lcd_path)
    try:
        from grove_rgb_lcd import *
        LCD_IMPORT_ERROR = None
    except ImportError as second_import_error:
        LCD_IMPORT_ERROR = second_import_error


Message = Tuple[str, str, Tuple[int, int, int]]


def get_lcd_functions() -> Tuple[Callable[[str], Any], Callable[[int, int, int], Any]]:
    """Return Grove LCD functions or exit with a clear import message."""
    set_text = globals().get("setText")
    set_rgb = globals().get("setRGB")
    if callable(set_text) and callable(set_rgb):
        return set_text, set_rgb

    print("Could not import grove_rgb_lcd.")
    print("Checked normal import and these paths:")
    for path in GROVE_LCD_PATHS:
        print("  " + path)
    if LCD_IMPORT_ERROR is not None:
        print("Import error: {}".format(LCD_IMPORT_ERROR))
    raise SystemExit(1)


def safe_set_rgb(
    set_rgb: Callable[[int, int, int], Any],
    red: int,
    green: int,
    blue: int,
) -> None:
    """Set LCD background color without crashing the script."""
    try:
        set_rgb(red, green, blue)
    except Exception as exc:
        print("LCD color error: {}".format(exc))


def safe_set_text(set_text: Callable[[str], Any], line_one: str, line_two: str) -> None:
    """Write two LCD lines without crashing the script."""
    # Printing the same text helps when the LCD is connected but hard to read.
    message = "{}\n{}".format(line_one, line_two)
    print("LCD MESSAGE:")
    print(line_one)
    print(line_two)
    try:
        set_text(message)
    except Exception as exc:
        print("LCD text error: {}".format(exc))


def show_message(
    set_text: Callable[[str], Any],
    set_rgb: Callable[[int, int, int], Any],
    message: Message,
) -> None:
    """Set LCD color and write a two-line message."""
    line_one, line_two, color = message
    safe_set_rgb(set_rgb, color[0], color[1], color[2])
    safe_set_text(set_text, line_one, line_two)


def clear_lcd(set_text: Callable[[str], Any]) -> None:
    """Clear the LCD if possible."""
    try:
        set_text("")
    except Exception as exc:
        print("LCD clear error: {}".format(exc))


def main() -> None:
    """Cycle through sample LCD messages until Ctrl+C."""
    parser = argparse.ArgumentParser(description="Test Grove RGB LCD.")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args()

    set_text, set_rgb = get_lcd_functions()
    messages = (
        # Line length is kept near the 16-character hardware limit.
        ("BIKE READY", "LCD TEST OK", (0, 128, 64)),
        ("Speed: 25 km/h", "Cad: 80 rpm", (0, 64, 255)),
        ("ALERT LEFT", "Car detected", (255, 0, 0)),
    )

    print("Testing Grove LCD. Press Ctrl+C to stop.")
    show_message(set_text, set_rgb, messages[0])
    time.sleep(3.0)

    try:
        index = 0
        while True:
            # Rotate messages so both color and text updates are tested.
            show_message(set_text, set_rgb, messages[index])
            index = (index + 1) % len(messages)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping LCD test.")
    finally:
        # Clear the display so stale test text is not left behind.
        clear_lcd(set_text)


if __name__ == "__main__":
    main()
