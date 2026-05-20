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

## Rider Feedback System

The old virtual buzzer field has been replaced with rider feedback fields in
the JSON message:

- `display_active`: whether a future LCD, RGB, or OLED display should show text
- `display_message`: text for a future LCD, RGB, or OLED display
- `speaker_message`: text for a future spoken warning
- `alert_level`: `normal`, `info`, `warning`, or `danger`
- `alert_side`: `none`, `left`, `right`, or `both`

The default state is blank and inactive: `display_active` is `false`,
`display_message` is empty, and `speaker_message` is empty. These fields are
virtual state only for now. No LCD, speaker, GPIO, AI, alert, database, or
dashboard code is included in this phase.

## Phase 6: Backend and SQLite Storage

Run the MQTT backend from the project root:

```bash
python main_backend.py
```

Then run the virtual bike MQTT publisher in another terminal:

```bash
python main_virtual_bike.py --mqtt
```

The backend subscribes to the sensor, status, and command topics and stores
messages in `data/bike_trainer.db`. The database layer also creates session,
settings, and future alerts tables, but it does not add AI rules, Streamlit,
hardware output, or external alerts.
