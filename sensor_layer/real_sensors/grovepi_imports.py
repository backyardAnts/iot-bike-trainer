"""Safe GrovePi and Grove LCD imports for Raspberry Pi hardware mode."""

from __future__ import annotations

import importlib
import sys
from typing import Any, Callable, Dict, Optional, Tuple


GROVEPI_PATHS = (
    "/home/pi/Dexter/GrovePi/Software/Python",
    "/home/pi/Dexter/GrovePi/Software/Python/grovepi",
    "/home/pi/Dexter/GrovePi/Software/Python/grove_rgb_lcd",
)

_grovepi_module = None  # type: Optional[Any]
_grovepi_error = None  # type: Optional[str]
_lcd_functions = None  # type: Optional[Tuple[Optional[Callable[..., Any]], Optional[Callable[..., Any]]]]
_lcd_error = None  # type: Optional[str]


def add_grovepi_paths() -> None:
    """Add common GrovePi install paths to sys.path once."""
    for path in GROVEPI_PATHS:
        if path not in sys.path:
            sys.path.append(path)


def load_grovepi() -> Optional[Any]:
    """Return the grovepi module, or None if it cannot be imported."""
    global _grovepi_module
    global _grovepi_error

    if _grovepi_module is not None:
        return _grovepi_module

    module, error = _import_module_with_grove_paths("grovepi")
    _grovepi_module = module
    _grovepi_error = error
    return _grovepi_module


def require_grovepi() -> Any:
    """Return grovepi or raise a clear error when hardware support is missing."""
    module = load_grovepi()
    if module is not None:
        return module

    raise RuntimeError(
        "Could not import grovepi. Install GrovePi or run this on the Raspberry Pi. "
        "Checked normal import and paths: {}. Error: {}".format(
            ", ".join(GROVEPI_PATHS),
            get_grovepi_error(),
        )
    )


def is_grovepi_available() -> bool:
    """Return True when grovepi can be imported."""
    return load_grovepi() is not None


def get_grovepi_error() -> Optional[str]:
    """Return the last GrovePi import error message."""
    return _grovepi_error


def load_lcd_functions() -> Tuple[
    Optional[Callable[..., Any]], Optional[Callable[..., Any]]
]:
    """Return Grove LCD setText and setRGB callables when available."""
    global _lcd_functions
    global _lcd_error

    if _lcd_functions is not None:
        return _lcd_functions

    module, error = _import_module_with_grove_paths("grove_rgb_lcd")
    if module is None:
        _lcd_error = error
        _lcd_functions = (None, None)
        return _lcd_functions

    set_text = getattr(module, "setText", None)
    set_rgb = getattr(module, "setRGB", None)
    if not callable(set_text) or not callable(set_rgb):
        _lcd_error = "grove_rgb_lcd imported, but setText/setRGB were not found"
        _lcd_functions = (None, None)
        return _lcd_functions

    _lcd_error = None
    _lcd_functions = (set_text, set_rgb)
    return _lcd_functions


def is_lcd_available() -> bool:
    """Return True when Grove LCD functions can be imported."""
    set_text, set_rgb = load_lcd_functions()
    return callable(set_text) and callable(set_rgb)


def get_lcd_error() -> Optional[str]:
    """Return the last Grove LCD import error message."""
    return _lcd_error


def get_import_status() -> Dict[str, Optional[str]]:
    """Return a small status dictionary useful for startup diagnostics."""
    load_grovepi()
    load_lcd_functions()
    return {
        "grovepi_available": str(_grovepi_module is not None),
        "grovepi_error": _grovepi_error,
        "lcd_available": str(_lcd_functions != (None, None)),
        "lcd_error": _lcd_error,
    }


def _import_module_with_grove_paths(
    module_name: str,
) -> Tuple[Optional[Any], Optional[str]]:
    first_error = None  # type: Optional[Exception]
    try:
        return importlib.import_module(module_name), None
    except ImportError as exc:
        first_error = exc

    add_grovepi_paths()

    try:
        return importlib.import_module(module_name), None
    except ImportError as second_error:
        return None, _format_import_error(module_name, first_error, second_error)


def _format_import_error(
    module_name: str,
    first_error: Optional[Exception],
    second_error: Exception,
) -> str:
    return (
        "failed to import {module_name}; normal import error: {first}; "
        "after adding GrovePi paths error: {second}"
    ).format(
        module_name=module_name,
        first=first_error,
        second=second_error,
    )
