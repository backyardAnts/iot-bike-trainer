-- Base SQLite schema for the bike trainer project.
-- The Python migration layer can add missing columns for older local databases,
-- but fresh installs start from this file.

-- Athletes stores optional rider profile data used for reports and HR rules.
CREATE TABLE IF NOT EXISTS athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    age INTEGER,
    height_cm REAL,
    weight_kg REAL,
    gender TEXT,
    fitness_level TEXT,
    max_heart_rate INTEGER,
    training_goal TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Raw sensor readings are the main time-series data from virtual or real bikes.
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
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
    received_at TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Status messages are stored raw so MQTT/session behavior can be audited later.
CREATE TABLE IF NOT EXISTS mqtt_status_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    device_id TEXT,
    session_id TEXT,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Commands are stored raw plus a normalized command name when one is available.
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    device_id TEXT,
    session_id TEXT,
    command TEXT,
    payload TEXT NOT NULL,
    received_at TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Sessions track active/stopped workout windows for a bike and athlete.
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    session_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    status TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Session metadata captures dashboard-provided rider and workout details.
CREATE TABLE IF NOT EXISTS session_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    session_id TEXT NOT NULL UNIQUE,
    device_id TEXT,
    workout_type TEXT,
    mode TEXT,
    athlete_name TEXT,
    athlete_age INTEGER,
    athlete_weight_kg REAL,
    athlete_height_cm REAL,
    athlete_email TEXT,
    athlete_gender TEXT,
    athlete_fitness_level TEXT,
    athlete_max_heart_rate INTEGER,
    athlete_training_goal TEXT,
    athlete_json TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Settings holds editable threshold values for later dashboard phases.
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Alerts is prepared for future high-level AI alerts.
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    timestamp TEXT NOT NULL,
    device_id TEXT,
    session_id TEXT,
    alert_type TEXT NOT NULL,
    alert_level TEXT NOT NULL,
    message TEXT NOT NULL,
    action TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Decision logs store every backend recommendation made from a sensor reading.
CREATE TABLE IF NOT EXISTS decision_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Session analytics stores calculated summary rows for reports and dashboards.
CREATE TABLE IF NOT EXISTS session_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Email tracking prevents duplicate stopped-session report sends.
CREATE TABLE IF NOT EXISTS session_report_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    session_id TEXT NOT NULL UNIQUE,
    workout_type TEXT,
    email_status TEXT NOT NULL,
    email_to TEXT,
    report_subject TEXT NOT NULL,
    report_body TEXT NOT NULL,
    error_message TEXT,
    generated_at TEXT NOT NULL,
    sent_at TEXT,
    FOREIGN KEY (athlete_id) REFERENCES athletes(id)
);

-- Indexes below keep recent-read, session, athlete, and report queries fast.
CREATE INDEX IF NOT EXISTS idx_athletes_email
ON athletes(email);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_received_at
ON sensor_readings(received_at);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_session
ON sensor_readings(session_id);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_athlete
ON sensor_readings(athlete_id);

CREATE INDEX IF NOT EXISTS idx_commands_received_at
ON commands(received_at);

CREATE INDEX IF NOT EXISTS idx_commands_session
ON commands(session_id);

CREATE INDEX IF NOT EXISTS idx_commands_athlete
ON commands(athlete_id);

CREATE INDEX IF NOT EXISTS idx_status_received_at
ON mqtt_status_messages(received_at);

CREATE INDEX IF NOT EXISTS idx_status_session
ON mqtt_status_messages(session_id);

CREATE INDEX IF NOT EXISTS idx_status_athlete
ON mqtt_status_messages(athlete_id);

CREATE INDEX IF NOT EXISTS idx_sessions_status
ON sessions(status);

CREATE INDEX IF NOT EXISTS idx_sessions_athlete
ON sessions(athlete_id);

CREATE INDEX IF NOT EXISTS idx_session_metadata_email
ON session_metadata(athlete_email);

CREATE INDEX IF NOT EXISTS idx_session_metadata_athlete
ON session_metadata(athlete_id);

CREATE INDEX IF NOT EXISTS idx_decision_logs_created_at
ON decision_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_decision_logs_session
ON decision_logs(session_id);

CREATE INDEX IF NOT EXISTS idx_decision_logs_athlete
ON decision_logs(athlete_id);

CREATE INDEX IF NOT EXISTS idx_decision_logs_alert_level
ON decision_logs(alert_level);

CREATE INDEX IF NOT EXISTS idx_session_analytics_session
ON session_analytics(session_id);

CREATE INDEX IF NOT EXISTS idx_session_analytics_athlete
ON session_analytics(athlete_id);

CREATE INDEX IF NOT EXISTS idx_session_analytics_created_at
ON session_analytics(created_at);

CREATE INDEX IF NOT EXISTS idx_session_report_emails_status
ON session_report_emails(email_status);

CREATE INDEX IF NOT EXISTS idx_session_report_emails_athlete
ON session_report_emails(athlete_id);
