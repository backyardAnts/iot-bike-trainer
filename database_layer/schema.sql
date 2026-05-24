CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    speed_kmh REAL NOT NULL,
    cadence_rpm INTEGER NOT NULL,
    heart_rate_bpm INTEGER NOT NULL,
    temperature_c REAL NOT NULL,
    left_distance_m REAL NOT NULL,
    right_distance_m REAL NOT NULL,
    display_active INTEGER NOT NULL,
    display_message TEXT NOT NULL,
    speaker_message TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    alert_side TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mqtt_status_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    device_id TEXT,
    session_id TEXT,
    alert_type TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    message TEXT NOT NULL,
    action TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    session_id TEXT,
    timestamp TEXT NOT NULL,
    workout_type TEXT,
    decision_type TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    alert_side TEXT,
    display_active INTEGER NOT NULL DEFAULT 0,
    display_message TEXT,
    speaker_message TEXT,
    recommended_action TEXT,
    source_topic TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    average_speed_kmh REAL NOT NULL,
    average_cadence_rpm REAL NOT NULL,
    average_heart_rate_bpm REAL NOT NULL,
    max_heart_rate_bpm INTEGER NOT NULL,
    min_heart_rate_bpm INTEGER NOT NULL,
    total_readings INTEGER NOT NULL,
    session_duration_seconds INTEGER NOT NULL,
    time_in_zone_easy INTEGER NOT NULL,
    time_in_zone_moderate INTEGER NOT NULL,
    time_in_zone_hard INTEGER NOT NULL,
    time_in_zone_peak INTEGER NOT NULL,
    improvement_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_received_at
ON sensor_readings(received_at);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_session
ON sensor_readings(session_id);

CREATE INDEX IF NOT EXISTS idx_commands_received_at
ON commands(received_at);

CREATE INDEX IF NOT EXISTS idx_status_received_at
ON mqtt_status_messages(received_at);

CREATE INDEX IF NOT EXISTS idx_sessions_status
ON sessions(status);

CREATE INDEX IF NOT EXISTS idx_decision_logs_created_at
ON decision_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_decision_logs_session
ON decision_logs(session_id);

CREATE INDEX IF NOT EXISTS idx_decision_logs_alert_level
ON decision_logs(alert_level);

CREATE INDEX IF NOT EXISTS idx_session_analytics_session
ON session_analytics(session_id);

CREATE INDEX IF NOT EXISTS idx_session_analytics_created_at
ON session_analytics(created_at);
