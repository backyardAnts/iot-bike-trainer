"""Run the Phase 6 MQTT backend and SQLite storage service."""

from __future__ import annotations

import time

from backend_layer.backend_service import BackendService
from backend_layer.mqtt_receiver import MqttBackendReceiver
from database_layer.db_connection import initialize_database
from database_layer.sqlite_storage import initialize_default_settings


def run_backend() -> None:
    """Initialize storage, connect to MQTT, and wait for messages."""
    initialize_database()
    initialize_default_settings()
    print("Database initialized.")

    backend_service = BackendService()
    receiver = MqttBackendReceiver(backend_service)

    try:
        receiver.start()
        print("Waiting for messages...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBackend stopping.")
    finally:
        receiver.stop()
        print("Backend stopped.")


if __name__ == "__main__":
    run_backend()
