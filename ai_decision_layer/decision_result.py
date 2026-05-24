"""Standard decision result returned by the local decision layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DecisionResult:
    """Decision output that can later be printed, stored, or sent over MQTT."""

    alert_level: str
    alert_side: str
    display_active: bool
    display_message: str
    speaker_message: str
    decision_type: str
    recommended_action: str
    workout_type: str

    def to_dict(self) -> dict[str, str | bool]:
        """Return the decision as a plain dictionary."""
        return asdict(self)
