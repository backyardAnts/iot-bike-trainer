# IoT Bike Trainer

Project architecture:

```text
iot-bike-trainer/
├── main_virtual_bike.py
├── main_session_analytics.py
├── reset_project_data.py
├── common/
│   ├── time_utils.py
│   ├── message_schema.py
│   └── session_manager.py
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
├── analytics_layer/
│   └── session_analytics.py
├── dashboard_layer/
│   └── streamlit_dashboard/
├── alert_layer/
│   └── email_or_sms_alerts/
├── config_layer/
│   ├── training_profiles.py
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

When no workout type is provided, the simulator asks you to choose one from
the terminal before readings start.

Run with a workout type directly:

```bash
python main_virtual_bike.py --workout cadence
```

Run a quick 10-reading schema check:

```bash
python main_virtual_bike.py --self-test
```

The virtual layer is intentionally separate from MQTT, SQLite, Streamlit,
alerts, and AI rules so it can later be replaced by real Raspberry Pi sensors
while keeping the same final message format.

## Phase 1: Training Goal Profiles

Workout profiles live in `config_layer/training_profiles.py`. The supported
workout types are `speed`, `cadence`, `endurance`, and `vo2_max`.

For now, the workout type is selected from the terminal or with the `--workout`
argument. Later, this selection can come from the application without changing
the virtual sensor logic.

Examples:

```bash
python main_virtual_bike.py
python main_virtual_bike.py --workout cadence
python main_virtual_bike.py --mqtt --workout endurance
```

Each generated sensor message includes the selected `workout_type`.

## Phase 2: Local Decision Layer

The local decision layer lives in `ai_decision_layer/`. It is rule-based for
now, not machine learning. Safety rules apply to all workouts, heart-rate rules
use the rider age from `config_layer/rider_profile.py`, and workout-specific
feedback depends on the selected workout type.

Run the simulator with local decisions:

```bash
python main_virtual_bike.py --workout cadence --decisions
python main_virtual_bike.py --workout speed --decisions
python main_virtual_bike.py --self-test
```

When `--decisions` is enabled, each reading is analyzed locally and printed
with a recommended action. This flag is still useful for local-only decision
testing without the backend.

## Phase 3: MQTT Backend Feedback Loop

The full MQTT flow connects the virtual bike, backend, rule-based decision
layer, and rider feedback fields:

```text
virtual bike publishes sensors
backend receives sensors
backend runs DecisionEngine
backend publishes update_feedback command
virtual bike receives command and updates feedback fields
```

Test it with two terminals.

Terminal 1:

```bash
python main_backend.py
```

Terminal 2:

```bash
python main_virtual_bike.py --mqtt --workout cadence
```

Expected behavior:

- The bike publishes sensor messages to `anthony/bike_001/sensors`.
- A paired Android phone can publish Samsung Watch 5 Pro heart-rate messages to
  `anthony/bike_001/heart_rate`.
- The backend saves valid sensor messages, runs the decision layer, and prints
  the selected decision.
- The backend publishes feedback commands to `anthony/bike_001/commands`.
- The virtual bike receives `update_feedback` commands and future sensor
  messages show updated `display_active`, `display_message`, `speaker_message`,
  `alert_level`, and `alert_side` fields.

Backend decisions are also written to SQLite by the Phase 4 decision log flow.
Analytics and dashboard/app support are planned for later phases.

## Real Raspberry Pi/GrovePi Hardware Mode

The project can now read physical GrovePi sensors and publish the same sensor
JSON format to MQTT.

Run real hardware mode with MQTT:

```bash
python3 main_virtual_bike.py --real --mqtt --interval 1
```

Alternative convenience entry point:

```bash
python3 main_real_bike.py --mqtt --interval 1
```

Hardware port assignments:

- D2: temperature/humidity sensor
- D3: speed Hall sensor
- D4: cadence Hall sensor
- D5: left ultrasonic sensor
- D6: right ultrasonic sensor
- D7: buzzer
- I2C: Grove LCD screen

Real mode uses the same MQTT client, broker settings, and sensor topic as
virtual mode. The default broker comes from `config_layer/settings.py` or the
same `.env` variables used by virtual mode; `--broker`, `--mqtt-port`, and
`--topic` are optional overrides.

Physical feedback is split between sensing, decision, and execution:

- Raspberry Pi sensors collect speed, cadence, temperature, and side-distance
  data.
- The backend AI/decision layer decides feedback for real hardware messages
  using the original physical controller rule: warn only when the left or right
  ultrasonic distance is below 50 cm.
- The backend publishes an `update_feedback` command with the warning side,
  buzzer state, and two LCD lines.
- The Raspberry Pi receives the command and only executes it on the buzzer and
  LCD.
- If MQTT/backend command feedback is unavailable, real mode falls back to the
  same extracted physical decision rule locally for safety.

Samsung Watch heart rate is integrated through the Android phone, not through
the Raspberry Pi. The watch measures heart rate, the paired phone publishes:

```json
{
  "device_id": "bike_001",
  "session_id": "session_XXX",
  "timestamp": "2026-05-26T12:00:00",
  "heart_rate_bpm": 128,
  "source": "samsung_watch_5_pro"
}
```

The backend subscribes to `anthony/bike_001/heart_rate`, caches the latest valid
heart-rate value per device/session, and merges recent values into bike sensor
messages before saving them to SQLite and running decisions. Expired values are
not reused indefinitely. This is for training feedback and analytics, not
medical diagnosis.

## Phase 4: Decision Logs in SQLite

The backend now stores every generated decision in the `decision_logs` table.
Each row records the device, session, sensor timestamp, workout type, decision
type, alert level, display message, speaker message, recommended action, source
MQTT topic, and creation time.

This prepares the project for future analytics, such as counting warnings,
tracking how often the rider was told to increase cadence, and comparing
sessions. Analytics and dashboard/app support are not implemented yet.

Run the full feedback loop:

Terminal 1:

```bash
python main_backend.py
```

Terminal 2:

```bash
python main_virtual_bike.py --mqtt --workout cadence
```

Inspect recent decision logs with the SQLite CLI:

```bash
sqlite3 data/bike_trainer.db
```

Then run:

```sql
SELECT id, timestamp, workout_type, decision_type, alert_level,
       recommended_action, display_message
FROM decision_logs
ORDER BY id DESC
LIMIT 10;
```

Or inspect with Python if the `sqlite3` CLI is unavailable:

```bash
python -c "import sqlite3; conn=sqlite3.connect('data/bike_trainer.db'); cur=conn.cursor(); print(cur.execute('SELECT id, timestamp, workout_type, decision_type, alert_level, recommended_action, display_message FROM decision_logs ORDER BY id DESC LIMIT 10').fetchall())"
```

Example row meaning: `workout_type=cadence`, `decision_type=workout`,
`alert_level=info`, and `recommended_action=increase_cadence` means the backend
decided the rider should increase cadence and sent that feedback to the bike.

## Dynamic Session IDs

Each simulator run automatically gets a new persistent `session_id`. The session
ID groups all sensor readings and backend decisions from one workout, which lets
Phase 5 analytics compare the current workout against previous workouts.

The counter is stored locally in `data/session_counter.txt`. If the last saved
number is `5`, the next automatic run uses `session_006`. A single simulator run
keeps the same session ID for every sensor message; the ID is not regenerated on
each reading.

Run with the next automatic session ID:

```bash
python main_virtual_bike.py --workout cadence
```

Override the session ID for testing:

```bash
python main_virtual_bike.py --workout cadence --session-id session_test_01
```

Startup output includes the selected session:

```text
Workout type: Cadence Training
Session ID: session_002
Virtual bike simulator started. Press Ctrl+C to stop.
```

## Starting Fresh

Reset local generated data when you want a clean database and want the next
automatic simulator run to start again at `session_001`:

```bash
python reset_project_data.py
```

The reset removes `data/bike_trainer.db` and `data/session_counter.txt` if they
exist, then recreates the SQLite database from `database_layer/schema.sql`.

## Phase 5: Session Analytics

The analytics layer lives in `analytics_layer/`. It calculates session-level
training statistics from stored SQLite sensor readings:

- average speed
- average cadence
- average heart rate
- min and max heart rate
- total readings
- session duration
- time in easy, moderate, hard, and peak heart-rate zones
- comparison against the previous session

Heart-rate zones are simple defaults for now:

- easy: heart rate below `120`
- moderate: `120` to `149`
- hard: `150` to `169`
- peak: `170` and above

Run the latest-session analytics demo:

```bash
python main_session_analytics.py
```

Analyze a specific session:

```bash
python main_session_analytics.py --session session_001
```

Print analytics without saving a summary row:

```bash
python main_session_analytics.py --no-save
```

Run the analytics self-test:

```bash
python main_session_analytics.py --self-test
```

The demo prints a readable report and saves a summary into the
`session_analytics` table by default. The saved table is a summary cache; the
source of truth remains the raw `sensor_readings` table.

Inspect saved analytics:

```sql
SELECT session_id, average_speed_kmh, average_cadence_rpm,
       average_heart_rate_bpm, improvement_message
FROM session_analytics
ORDER BY id DESC
LIMIT 10;
```

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
python main_virtual_bike.py --mqtt --workout endurance
```

The backend subscribes to the sensor, heart-rate, status, and command topics and stores
messages in `data/bike_trainer.db`. Current phases also store decision logs and
optional session analytics summaries. Real hardware mode can execute backend
feedback commands on the buzzer/LCD; Streamlit, external alerts, and advanced
analytics are still future work.
