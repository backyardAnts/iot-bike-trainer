"""Standard decision result returned by the local decision layer.

The same object can drive the LCD, MQTT feedback, saved decision logs, and
human-readable terminal output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionResult:
    """Decision output that can later be printed, stored, or sent over MQTT."""

    # Core alert fields used by storage, MQTT, and the UI.
    alert_level: str
    alert_side: str
    display_active: bool
    display_message: str
    speaker_message: str
    decision_type: str
    recommended_action: str
    workout_type: str

    # Hardware-facing fields are optional because virtual decisions may not
    # need an LCD line or buzzer pulse.
    lcd_line_1: str = ""
    lcd_line_2: str = ""
    buzzer_state: bool = False
    led_state: bool = False
    buzzer_pulse_ms: int = 0
    buzzer_pulse_reason: str = ""
    heart_rate_bpm: int = 0
    hr_percent: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the decision as a plain dictionary."""
        return asdict(self)
