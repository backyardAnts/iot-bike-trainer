"""Global safety and health thresholds for rule-based decisions."""

## this files defines the thresholds for the AI. The HR is a percentage value since everyone has a different max HR
## The HR also should change based on what kind of workout he is doing
SIDE_DISTANCE_WARNING_M = 1.5
SIDE_DISTANCE_DANGER_M = 0.8

TEMPERATURE_WARNING_C = 32.0
TEMPERATURE_DANGER_C = 38.0

HR_WARNING_PERCENT_OF_MAX = 0.85
HR_DANGER_PERCENT_OF_MAX = 0.92

HR_ZONES = {
    "endurance": {
        "min_percent": 0.60,
        "max_percent": 0.75,
    },
    "moderate": {
        "min_percent": 0.65,
        "max_percent": 0.80,
    },
    "high": {
        "min_percent": 0.75,
        "max_percent": 0.88,
    },
    "very_high": {
        "min_percent": 0.85,
        "max_percent": 0.95,
    },
}

# Backward-compatible names used by earlier simulator/storage code.
DANGER_DISTANCE_M = 1.0
LOW_CADENCE_RPM = 60
HIGH_CADENCE_RPM = 105
HIGH_HEART_RATE_BPM = 170
HIGH_TEMPERATURE_C = 35
