"""MQTT topic names used by the bike trainer project."""

## this file defines the mqtt topics that will be used accross our application
SENSOR_TOPIC = "anthony/bike_001/sensors"
COMMAND_TOPIC = "anthony/bike_001/commands"
STATUS_TOPIC = "anthony/bike_001/status"
SESSION_TOPIC = "anthony/bike_001/session"
ALERT_TOPIC = "anthony/bike_001/alerts"
HEART_RATE_TOPIC = "anthony/bike_001/heart_rate"
MERGED_SENSORS_TOPIC = "anthony/bike_001/merged_sensors"

ALL_TOPICS = {
    "sensors": SENSOR_TOPIC,
    "commands": COMMAND_TOPIC,
    "status": STATUS_TOPIC,
    "session": SESSION_TOPIC,
    "alerts": ALERT_TOPIC,
    "heart_rate": HEART_RATE_TOPIC,
    "merged_sensors": MERGED_SENSORS_TOPIC,
}
