# IoT Bike Trainer

Project architecture:

```text
iot-bike-trainer/
├── main_virtual_bike.py
├── common/
│   ├── time_utils.py
│   └── message_schema.py
├── sensor_layer/
│   ├── virtual_sensors/
│   └── real_sensors_later/
├── mqtt_layer/
│   ├── publisher/
│   └── subscriber/
├── backend_layer/
│   └── mqtt_receiver/
├── database_layer/
│   └── sqlite_storage/
├── ai_decision_layer/
│   └── physical_ai_rules/
├── dashboard_layer/
│   └── streamlit_dashboard/
├── alert_layer/
│   └── email_or_sms_alerts/
├── config_layer/
│   ├── settings.py
│   ├── thresholds.py
│   └── thresholds_and_settings/
└── README.md
```

## Phase 3: Virtual Sensor System

Phase 3 runs without Raspberry Pi hardware and uses only the Python standard
library. It produces one JSON-ready virtual bike sensor message per second.

Run the simulator from the project root:

```bash
python main_virtual_bike.py
```

Run a quick 10-reading schema check:

```bash
python main_virtual_bike.py --self-test
```

The virtual layer is intentionally separate from MQTT, SQLite, Streamlit,
alerts, and AI rules so it can later be replaced by real Raspberry Pi sensors
while keeping the same final message format.
