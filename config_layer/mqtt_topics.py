"""MQTT topic names used by the bike trainer project.

Keeping topics in one file prevents the simulator, backend, and tests from
drifting apart.
"""

# Device-scoped topics for sensor data, commands, session status, and alerts.
SENSOR_TOPIC = "anthony/bike_001/sensors"
COMMAND_TOPIC = "anthony/bike_001/commands"
STATUS_TOPIC = "anthony/bike_001/status"
SESSION_TOPIC = "anthony/bike_001/session"
ALERT_TOPIC = "anthony/bike_001/alerts"
HEART_RATE_TOPIC = "anthony/bike_001/heart_rate"
MERGED_SENSORS_TOPIC = "anthony/bike_001/merged_sensors"

ALL_TOPICS = {
    # Useful when code needs to iterate over every known topic.
    "sensors": SENSOR_TOPIC,
    "commands": COMMAND_TOPIC,
    "status": STATUS_TOPIC,
    "session": SESSION_TOPIC,
    "alerts": ALERT_TOPIC,
    "heart_rate": HEART_RATE_TOPIC,
    "merged_sensors": MERGED_SENSORS_TOPIC,
}
