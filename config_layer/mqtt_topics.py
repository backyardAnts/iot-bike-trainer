"""MQTT topic names used by the bike trainer project."""

## this file defines the mqtt topics that will be used accross our application
SENSOR_TOPIC = "anthony/bike_001/sensors"
COMMAND_TOPIC = "anthony/bike_001/commands"
STATUS_TOPIC = "anthony/bike_001/status"
ALERT_TOPIC = "anthony/bike_001/alerts"

ALL_TOPICS = {
    "sensors": SENSOR_TOPIC,
    "commands": COMMAND_TOPIC,
    "status": STATUS_TOPIC,
    "alerts": ALERT_TOPIC,
}
