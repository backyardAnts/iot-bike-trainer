"""Run the Phase 3 virtual bike sensor simulator."""

from __future__ import annotations

import argparse
import time
from typing import Any, Optional

from ai_decision_layer.decision_engine import DecisionEngine
from ai_decision_layer.decision_result import DecisionResult
from common.message_schema import message_to_json, validate_sensor_message
from config_layer.settings import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_SAMPLE_INTERVAL_SECONDS,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
)
from config_layer.training_profiles import (
    DEFAULT_WORKOUT_TYPE,
    TRAINING_PROFILES,
    WORKOUT_TYPES,
    get_training_profile,
    is_valid_workout_type,
    normalize_workout_type,
)
from sensor_layer.virtual_sensors.virtual_bike import VirtualBike


def run_forever(
    workout_type: str,
    session_id: str | None = None,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    decisions: bool = False,
) -> None:
    """Print one JSON sensor message per sample interval until Ctrl+C."""
    bike = VirtualBike(
        session_id=session_id,
        workout_type=workout_type,
        random_seed=random_seed,
    )
    profile = get_training_profile(bike.workout_type)
    decision_engine = DecisionEngine() if decisions else None
    print(f"Workout type: {profile['display_name']}")
    print(f"Session ID: {bike.session_id}")
    print("Virtual bike simulator started. Press Ctrl+C to stop.")

    try:
        while True:
            message = bike.update()
            print_sensor_output(message, decision_engine)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nVirtual bike simulator stopped.")


def run_mqtt_mode(
    workout_type: str,
    session_id: str | None = None,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    decisions: bool = False,
) -> None:
    """Publish virtual bike readings to MQTT while also printing locally."""
    from config_layer.mqtt_topics import SENSOR_TOPIC
    from mqtt_layer.command_handler import CommandHandler
    from mqtt_layer.mqtt_client import create_mqtt_client
    from mqtt_layer.publisher import MqttPublisher
    from mqtt_layer.subscriber import MqttCommandSubscriber

    bike = VirtualBike(
        session_id=session_id,
        workout_type=workout_type,
        random_seed=random_seed,
    )
    profile = get_training_profile(bike.workout_type)
    decision_engine = DecisionEngine() if decisions else None
    client: Any | None = None
    subscriber: MqttCommandSubscriber | None = None
    publisher: MqttPublisher | None = None

    try:
        client = create_mqtt_client()
        publisher = MqttPublisher(client)
        command_handler = CommandHandler(bike)
        subscriber = MqttCommandSubscriber(client, command_handler)

        client.loop_start()
        subscriber.start()

        publisher.publish_status(
            "started",
            {
                "device_id": bike.device_id,
                "session_id": bike.session_id,
                "workout_type": bike.workout_type,
            },
        )
        print(f"Workout type: {profile['display_name']}")
        print(f"Session ID: {bike.session_id}")
        print(f"MQTT broker: {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}")
        print(f"MQTT sensor topic: {SENSOR_TOPIC}")
        print("Virtual bike MQTT simulator started. Press Ctrl+C to stop.")

        while True:
            message = bike.update()
            publisher.publish_json(SENSOR_TOPIC, message)
            print_sensor_output(message, decision_engine)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nVirtual bike MQTT simulator stopping.")
    finally:
        if publisher is not None:
            publisher.publish_status(
                "stopped",
                {
                    "device_id": bike.device_id,
                    "session_id": bike.session_id,
                    "workout_type": bike.workout_type,
                },
            )
        if subscriber is not None:
            subscriber.stop()
        if client is not None:
            client.loop_stop()
            client.disconnect()
        print("Virtual bike MQTT simulator stopped.")


def run_real_mode(
    workout_type: str = DEFAULT_WORKOUT_TYPE,
    session_id: Optional[str] = None,
    interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    mqtt_enabled: bool = False,
    broker_host: Optional[str] = None,
    broker_port: Optional[int] = None,
    sensor_topic: Optional[str] = None,
    heart_rate_bpm: int = 0,
    lcd_enabled: bool = True,
    lcd_debug: bool = False,
    wheel_diameter_cm: float = 70.0,
    speed_magnets_per_rotation: int = 1,
    cadence_magnets_per_rotation: int = 1,
    enable_hall: bool = True,
    hall_debug: bool = False,
    enable_temperature: bool = True,
    temperature_sensor_type: int = 0,
    temperature_debug: bool = False,
) -> None:
    """Read physical GrovePi sensors and optionally publish them to MQTT."""
    from config_layer.mqtt_topics import MERGED_SENSORS_TOPIC, SENSOR_TOPIC
    from mqtt_layer.command_handler import CommandHandler
    from mqtt_layer.publisher import MqttPublisher
    from mqtt_layer.subscriber import MqttCommandSubscriber
    from sensor_layer.real_sensors.real_bike import RealBike

    bike = RealBike(
        session_id=session_id,
        workout_type=workout_type,
        heart_rate_bpm=heart_rate_bpm,
        lcd_enabled=lcd_enabled,
        lcd_debug=lcd_debug,
        wheel_diameter_cm=wheel_diameter_cm,
        speed_magnets_per_rotation=speed_magnets_per_rotation,
        cadence_magnets_per_rotation=cadence_magnets_per_rotation,
        enable_hall=enable_hall,
        hall_debug=hall_debug,
        enable_temperature=enable_temperature,
        temperature_sensor_type=temperature_sensor_type,
        temperature_debug=temperature_debug,
        command_feedback_enabled=mqtt_enabled,
        command_timeout_seconds=max(3.0, float(interval_seconds) * 3.0),
    )
    profile = get_training_profile(bike.workout_type)
    topic = sensor_topic or SENSOR_TOPIC
    client: Any | None = None
    publisher: MqttPublisher | None = None
    subscriber: MqttCommandSubscriber | None = None
    command_handler: Any | None = None

    try:
        if mqtt_enabled:
            try:
                from mqtt_layer.mqtt_client import create_mqtt_client

                client = create_mqtt_client(
                    broker_host=broker_host,
                    broker_port=broker_port,
                )
                publisher = MqttPublisher(client)
                command_handler = CommandHandler(bike, defer_application=True)
                subscriber = MqttCommandSubscriber(
                    client,
                    command_handler,
                    merged_sensor_handler=_print_merged_sensor_output,
                )
                client.loop_start()
                subscriber.start()
                bike.set_command_feedback_enabled(True)
                publisher.publish_status(
                    "started",
                    {
                        "device_id": bike.device_id,
                        "session_id": bike.session_id,
                        "workout_type": bike.workout_type,
                        "mode": "real",
                    },
                )
            except Exception as exc:
                print(f"MQTT unavailable; continuing with local fallback: {exc}")
                bike.set_command_feedback_enabled(False)

        print("Real GrovePi bike mode started. Press Ctrl+C to stop.")
        print(f"Workout type: {profile['display_name']}")
        print(f"Session ID: {bike.session_id}")
        active_hardware = ["ultrasonic D5/D6", "buzzer D7"]
        if lcd_enabled:
            active_hardware.append("LCD I2C")
        if enable_hall:
            active_hardware.append("Hall D3/D4")
        if enable_temperature:
            active_hardware.append("temperature D2")
        print("Active hardware: {}".format(", ".join(active_hardware)))
        print("Hall sensors: {}".format("enabled" if enable_hall else "disabled"))
        print(
            "Temperature sensor: {}".format(
                "enabled" if enable_temperature else "disabled"
            )
        )
        if mqtt_enabled and publisher is not None:
            mqtt_host = broker_host or MQTT_BROKER_HOST
            mqtt_port = broker_port if broker_port is not None else MQTT_BROKER_PORT
            print(f"MQTT broker: {mqtt_host}:{mqtt_port}")
            print(f"Publishing RAW real sensor JSON to MQTT topic: {topic}")
            print(
                "Receiving backend merged sensor JSON from MQTT topic: "
                f"{MERGED_SENSORS_TOPIC}"
            )
            print("Receiving backend feedback commands for buzzer/LCD.")
        elif mqtt_enabled:
            print("MQTT unavailable; real sensor JSON will only print locally.")

        bike.show_startup_lcd_message()
        if lcd_enabled:
            time.sleep(2.0)

        while True:
            _apply_pending_real_command(command_handler)
            message = bike.update()
            status_line = bike.get_latest_status_line()
            if status_line:
                print(status_line, flush=True)
            raw_json = message_to_json(message)
            if publisher is not None:
                print(f"RAW sensor JSON: {raw_json}", flush=True)
            else:
                print(raw_json, flush=True)
            if not validate_sensor_message(message):
                print("Warning: real sensor message failed schema validation.")
            if publisher is not None:
                publisher.publish_json(topic, message)
            _apply_pending_real_command(command_handler)
            bike.wait_between_updates(interval_seconds)
    except KeyboardInterrupt:
        print("\nReal GrovePi bike mode stopping.")
    finally:
        if publisher is not None:
            publisher.publish_status(
                "stopped",
                {
                    "device_id": bike.device_id,
                    "session_id": bike.session_id,
                    "workout_type": bike.workout_type,
                    "mode": "real",
                },
            )
        if subscriber is not None:
            subscriber.stop()
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as exc:
                print(f"MQTT cleanup failed: {exc}")
        bike.cleanup()
        print("Real GrovePi bike mode stopped.")


def _apply_pending_real_command(command_handler: Any | None) -> None:
    """Apply one queued real-bike MQTT command on the main hardware loop."""
    if command_handler is None:
        return
    if not hasattr(command_handler, "apply_latest_command"):
        return

    result = command_handler.apply_latest_command()
    if result is not None:
        print(f"Command result: {result}", flush=True)


def _print_merged_sensor_output(payload: bytes) -> None:
    """Print backend-processed sensor JSON received from MQTT."""
    payload_text = payload.decode("utf-8", errors="replace")
    print(f"MERGED sensor JSON: {payload_text}", flush=True)


def run_self_test(reading_count: int = 10) -> None:
    """Run a short deterministic simulation and validate each message."""
    run_session_id_self_test()

    print("Testing valid workout types.")
    for workout_type in WORKOUT_TYPES:
        bike = VirtualBike(
            session_id=f"self_test_{workout_type}",
            workout_type=workout_type,
            random_seed=42,
        )
        message = bike.update()
        if message.get("workout_type") != workout_type:
            raise RuntimeError(f"Unexpected workout type in message: {message}")
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")

    try:
        VirtualBike(session_id="self_test_invalid", workout_type="invalid")
    except ValueError:
        print("Invalid workout type rejected.")
    else:
        raise RuntimeError("Invalid workout type was accepted.")

    bike = VirtualBike(
        session_id="self_test_endurance",
        workout_type="endurance",
        random_seed=42,
    )
    print(f"Running virtual bike self-test for {reading_count} readings.")

    for _ in range(reading_count):
        message = bike.update()
        if "workout_type" not in message:
            raise RuntimeError(f"Missing workout_type in sensor message: {message}")
        if not validate_sensor_message(message):
            raise RuntimeError(f"Invalid sensor message: {message}")
        print(message_to_json(message))

    run_decision_self_test()
    print("Self-test passed.")


def run_session_id_self_test() -> None:
    """Verify persistent session ID generation without using project data."""
    import tempfile
    from pathlib import Path

    from common.session_manager import (
        format_session_id,
        get_next_session_id,
        read_current_session_number,
        reset_session_counter,
        save_current_session_number,
    )

    print("Testing dynamic session IDs.")
    with tempfile.TemporaryDirectory() as temp_dir:
        counter_path = Path(temp_dir) / "session_counter.txt"

        if get_next_session_id(counter_path) != "session_001":
            raise RuntimeError("First generated session ID was not session_001.")
        if get_next_session_id(counter_path) != "session_002":
            raise RuntimeError("Second generated session ID was not session_002.")
        if read_current_session_number(counter_path) != 2:
            raise RuntimeError("Session counter did not save the current number.")
        if format_session_id(10) != "session_010":
            raise RuntimeError("Session ID zero-padding is incorrect.")

        save_current_session_number(5, counter_path)
        if get_next_session_id(counter_path) != "session_006":
            raise RuntimeError("Session counter did not continue from saved value.")

        reset_session_counter(counter_path)
        if get_next_session_id(counter_path) != "session_001":
            raise RuntimeError("Session counter reset did not restart at session_001.")

        reset_session_counter(counter_path)
        bike = VirtualBike(
            workout_type="cadence",
            random_seed=42,
            session_counter_file=counter_path,
        )
        first_message = bike.update()
        second_message = bike.update()
        if bike.session_id != "session_001":
            raise RuntimeError("VirtualBike did not use the generated session ID.")
        if first_message["session_id"] != bike.session_id:
            raise RuntimeError("First message did not include bike session ID.")
        if second_message["session_id"] != bike.session_id:
            raise RuntimeError("VirtualBike changed session ID between updates.")

        reset_session_counter(counter_path)
        first_bike = VirtualBike(
            workout_type="cadence",
            random_seed=42,
            session_counter_file=counter_path,
        )
        second_bike = VirtualBike(
            workout_type="cadence",
            random_seed=42,
            session_counter_file=counter_path,
        )
        if first_bike.session_id != "session_001":
            raise RuntimeError("First separate bike did not get session_001.")
        if second_bike.session_id != "session_002":
            raise RuntimeError("Second separate bike did not get session_002.")

        explicit_bike = VirtualBike(
            session_id="session_test_01",
            workout_type="cadence",
            random_seed=42,
            session_counter_file=counter_path,
        )
        explicit_message = explicit_bike.update()
        if explicit_bike.session_id != "session_test_01":
            raise RuntimeError("Explicit session ID was not preserved.")
        if explicit_message["session_id"] != "session_test_01":
            raise RuntimeError("Explicit session ID was not written to messages.")


def run_decision_self_test() -> None:
    """Run simple local decision-layer checks."""
    print("Testing decision layer.")
    decision_engine = DecisionEngine()

    low_cadence_decision = decision_engine.analyze(
        make_test_sensor_message(
            workout_type="cadence",
            cadence_rpm=50,
            speed_kmh=20,
            heart_rate_bpm=120,
        )
    )
    if low_cadence_decision.recommended_action != "pedal_faster":
        raise RuntimeError(f"Unexpected low cadence decision: {low_cadence_decision}")

    good_cadence_decision = decision_engine.analyze(
        make_test_sensor_message(
            workout_type="cadence",
            cadence_rpm=85,
            speed_kmh=20,
            heart_rate_bpm=120,
        )
    )
    if good_cadence_decision.recommended_action != "keep_cadence":
        raise RuntimeError(f"Unexpected good cadence decision: {good_cadence_decision}")

    right_danger_decision = decision_engine.analyze(
        make_test_sensor_message(
            workout_type="speed",
            cadence_rpm=90,
            speed_kmh=10,
            heart_rate_bpm=120,
            right_distance_m=0.49,
        )
    )
    if (
        right_danger_decision.decision_type != "physical_safety"
        or right_danger_decision.alert_level != "warning"
        or right_danger_decision.recommended_action != "object_right"
    ):
        raise RuntimeError(f"Unexpected safety decision: {right_danger_decision}")

    high_hr_decision = decision_engine.analyze(
        make_test_sensor_message(
            workout_type="vo2_max",
            cadence_rpm=95,
            speed_kmh=24,
            heart_rate_bpm=185,
        )
    )
    if (
        high_hr_decision.decision_type != "workout_guidance"
        or high_hr_decision.recommended_action != "recover"
    ):
        raise RuntimeError(f"Unexpected VO2 max decision: {high_hr_decision}")

    try:
        decision_engine.analyze(
            make_test_sensor_message(
                workout_type="invalid",
                cadence_rpm=80,
                speed_kmh=20,
                heart_rate_bpm=120,
            )
        )
    except ValueError:
        print("Invalid decision workout type rejected.")
    else:
        raise RuntimeError("Invalid decision workout type was accepted.")

    run_decision_log_storage_self_test(low_cadence_decision)
    run_backend_feedback_self_test(low_cadence_decision)


def run_decision_log_storage_self_test(decision: DecisionResult) -> None:
    """Verify decision log storage against a temporary SQLite database."""
    import sqlite3
    import tempfile
    from contextlib import contextmanager
    from pathlib import Path

    from database_layer.db_connection import SCHEMA_PATH
    from database_layer import sqlite_storage

    sensor_message = make_test_sensor_message(
        workout_type="cadence",
        cadence_rpm=50,
        speed_kmh=20,
        heart_rate_bpm=120,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "bike_trainer_test.db"

        @contextmanager
        def get_test_db_connection():
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

        with get_test_db_connection() as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        original_get_db_connection = sqlite_storage.get_db_connection
        sqlite_storage.get_db_connection = get_test_db_connection
        try:
            sqlite_storage.initialize_default_settings()
            sqlite_storage.save_sensor_reading(sensor_message)
            sqlite_storage.save_decision_log(
                sensor_message,
                decision,
                source_topic="anthony/bike_001/sensors",
            )
        finally:
            sqlite_storage.get_db_connection = original_get_db_connection

        with get_test_db_connection() as connection:
            decision_row = connection.execute(
                """
                SELECT display_active, recommended_action, source_topic
                FROM decision_logs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            sensor_count = connection.execute(
                "SELECT COUNT(*) AS count FROM sensor_readings"
            ).fetchone()["count"]

    if decision_row is None:
        raise RuntimeError("Decision log row was not inserted.")
    if int(decision_row["display_active"]) != 1:
        raise RuntimeError("Decision display_active was not stored as 1.")
    if decision_row["recommended_action"] != decision.recommended_action:
        raise RuntimeError("Decision recommended_action was not stored.")
    if decision_row["source_topic"] != "anthony/bike_001/sensors":
        raise RuntimeError("Decision source_topic was not stored.")
    if sensor_count != 1:
        raise RuntimeError("Sensor reading self-test insert failed.")


def run_backend_feedback_self_test(decision: DecisionResult) -> None:
    """Run simple feedback-command checks without a real MQTT broker."""
    from backend_layer.backend_service import build_feedback_command
    from backend_layer.mqtt_receiver import MqttBackendReceiver
    from config_layer.mqtt_topics import (
        COMMAND_TOPIC,
        MERGED_SENSORS_TOPIC,
        SENSOR_TOPIC,
        STATUS_TOPIC,
    )
    from mqtt_layer.command_handler import CommandHandler

    feedback_command = build_feedback_command(decision)
    if feedback_command["command"] != "update_feedback":
        raise RuntimeError(f"Unexpected feedback command: {feedback_command}")

    bike = VirtualBike(
        session_id="self_test_feedback",
        workout_type="cadence",
        random_seed=42,
    )
    command_result = CommandHandler(bike).handle_command(feedback_command)
    if not command_result["ok"]:
        raise RuntimeError(f"Feedback command was rejected: {command_result}")
    if bike.display_message != decision.display_message:
        raise RuntimeError("Feedback command did not update bike display message.")

    receiver = MqttBackendReceiver(_FakeBackendService(feedback_command))
    fake_publisher = _FakePublisher()
    receiver.publisher = fake_publisher

    receiver._on_message(None, None, _FakeMqttMessage(SENSOR_TOPIC, b"{}"))
    if fake_publisher.publish_count != 2:
        raise RuntimeError("Sensor message did not publish merged data and feedback.")
    if fake_publisher.published_topics != [MERGED_SENSORS_TOPIC, COMMAND_TOPIC]:
        raise RuntimeError("Feedback command was published to the wrong topic.")

    receiver._on_message(None, None, _FakeMqttMessage(COMMAND_TOPIC, b"{}"))
    receiver._on_message(None, None, _FakeMqttMessage(STATUS_TOPIC, b"{}"))
    if fake_publisher.publish_count != 2:
        raise RuntimeError("Command/status message published unexpected feedback.")


class _FakeBackendService:
    def __init__(self, feedback_command: dict[str, Any]) -> None:
        self.feedback_command = feedback_command

    def handle_sensor_message(
        self,
        payload: bytes,
        source_topic: str | None = None,
    ) -> dict[str, Any]:
        return self.feedback_command

    def get_latest_merged_sensor_message(self) -> dict[str, Any]:
        return make_test_sensor_message(
            workout_type="cadence",
            cadence_rpm=50,
            speed_kmh=20,
            heart_rate_bpm=120,
        )

    def handle_command_message(self, payload: bytes) -> None:
        return None

    def handle_status_message(self, topic: str, payload: bytes) -> None:
        return None


class _FakePublisher:
    def __init__(self) -> None:
        self.publish_count = 0
        self.last_topic: str | None = None
        self.last_payload: dict[str, Any] | None = None
        self.published_topics: list[str] = []

    def publish_json(self, topic: str, payload: dict[str, Any]) -> bool:
        self.publish_count += 1
        self.last_topic = topic
        self.last_payload = payload
        self.published_topics.append(topic)
        return True


class _FakeMqttMessage:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


def make_test_sensor_message(
    workout_type: str,
    cadence_rpm: int,
    speed_kmh: float,
    heart_rate_bpm: int,
    left_distance_m: float = 3.0,
    right_distance_m: float = 3.0,
    temperature_c: float = 25.0,
) -> dict[str, Any]:
    """Build a minimal sensor message for deterministic self-test cases."""
    return {
        "device_id": "bike_001",
        "timestamp": "self-test",
        "session_id": "session_001",
        "workout_type": workout_type,
        "speed_kmh": speed_kmh,
        "cadence_rpm": cadence_rpm,
        "heart_rate_bpm": heart_rate_bpm,
        "temperature_c": temperature_c,
        "left_distance_m": left_distance_m,
        "right_distance_m": right_distance_m,
        "display_active": False,
        "display_message": "",
        "speaker_message": "",
        "alert_level": "normal",
        "alert_side": "none",
    }


def print_sensor_output(
    message: dict[str, Any],
    decision_engine: DecisionEngine | None = None,
) -> None:
    """Print the normal JSON output, or readable sensor plus decision output."""
    if decision_engine is None:
        print(message_to_json(message), flush=True)
        return

    decision = decision_engine.analyze(message)
    print(
        "Sensor: "
        f"cadence={message['cadence_rpm']} rpm, "
        f"speed={message['speed_kmh']} km/h, "
        f"heart_rate={message['heart_rate_bpm']} bpm",
        flush=True,
    )
    print(format_decision(decision), flush=True)


def format_decision(decision: DecisionResult) -> str:
    """Return a compact terminal-friendly decision summary."""
    return (
        f"Decision: {decision.display_message} "
        f"| alert={decision.alert_level} "
        f"| action={decision.recommended_action}"
    )


def choose_workout_type(workout_type: str | None = None) -> str:
    """Return a validated workout type from CLI input or an interactive menu."""
    if workout_type is not None:
        if is_valid_workout_type(workout_type):
            return normalize_workout_type(workout_type)
        supported = ", ".join(WORKOUT_TYPES)
        raise ValueError(
            f"Invalid workout type: {workout_type}. "
            f"Choose one of: {supported}."
        )

    while True:
        print("\nChoose workout type:")
        for index, profile_workout_type in enumerate(WORKOUT_TYPES, start=1):
            profile = TRAINING_PROFILES[profile_workout_type]
            print(f"{index}. {profile['display_name']}")

        selected = input("Enter number or workout type: ").strip()
        if selected.isdigit():
            selected_index = int(selected)
            if 1 <= selected_index <= len(WORKOUT_TYPES):
                return WORKOUT_TYPES[selected_index - 1]

        if is_valid_workout_type(selected):
            return normalize_workout_type(selected)

        supported = ", ".join(WORKOUT_TYPES)
        print(
            f"Invalid workout type. Choose 1-{len(WORKOUT_TYPES)} "
            f"or one of: {supported}."
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Virtual bike simulator")
    parser.add_argument(
        "--real",
        action="store_true",
        help="read physical Raspberry Pi/GrovePi sensors instead of virtual sensors",
    )
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="publish bike sensor messages to MQTT",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="print 10 readings and validate the output schema",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help="sample interval in seconds",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="optional random seed for repeatable virtual readings",
    )
    parser.add_argument(
        "--workout",
        metavar="{speed,cadence,endurance,vo2_max}",
        help="workout type to simulate",
    )
    parser.add_argument(
        "--session-id",
        help="optional explicit session ID for this simulator run",
    )
    parser.add_argument(
        "--heart-rate",
        type=int,
        default=0,
        help="placeholder heart rate value for real hardware mode",
    )
    parser.add_argument(
        "--broker",
        help=(
            "optional MQTT broker host override for real hardware mode "
            f"(default: {MQTT_BROKER_HOST})"
        ),
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        help=(
            "optional MQTT broker port override for real hardware mode "
            f"(default: {MQTT_BROKER_PORT})"
        ),
    )
    parser.add_argument(
        "--topic",
        help="MQTT sensor topic for real hardware mode",
    )
    parser.add_argument(
        "--wheel-diameter-cm",
        type=float,
        default=70.0,
        help="wheel diameter in centimeters for real speed Hall sensor",
    )
    parser.add_argument(
        "--speed-magnets-per-rotation",
        type=int,
        default=1,
        help="speed Hall magnet passes per wheel rotation",
    )
    parser.add_argument(
        "--cadence-magnets-per-rotation",
        type=int,
        default=1,
        help="cadence Hall magnet passes per crank rotation",
    )
    parser.add_argument(
        "--enable-hall",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-hall",
        action="store_true",
        help="disable real D3/D4 Hall speed and cadence sensors",
    )
    parser.add_argument(
        "--hall-debug",
        action="store_true",
        help="print real Hall sensor raw values and event counts",
    )
    parser.add_argument(
        "--temperature-sensor-type",
        type=int,
        default=0,
        help="Grove DHT sensor type for real temperature sensor on D2",
    )
    parser.add_argument(
        "--no-temperature",
        action="store_true",
        help="disable real temperature/humidity sensor on D2",
    )
    parser.add_argument(
        "--temperature-debug",
        action="store_true",
        help="print real temperature raw readings and fallback information",
    )
    parser.add_argument(
        "--decisions",
        action="store_true",
        help="print local rule-based decisions for each sensor reading",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        if args.self_test:
            run_self_test()
        elif args.real:
            selected_workout_type = (
                choose_workout_type(args.workout)
                if args.workout is not None
                else DEFAULT_WORKOUT_TYPE
            )
            run_real_mode(
                workout_type=selected_workout_type,
                session_id=args.session_id,
                interval_seconds=args.interval,
                mqtt_enabled=args.mqtt,
                broker_host=args.broker,
                broker_port=args.mqtt_port,
                sensor_topic=args.topic,
                heart_rate_bpm=args.heart_rate,
                wheel_diameter_cm=args.wheel_diameter_cm,
                speed_magnets_per_rotation=args.speed_magnets_per_rotation,
                cadence_magnets_per_rotation=args.cadence_magnets_per_rotation,
                enable_hall=not args.no_hall,
                hall_debug=args.hall_debug,
                enable_temperature=not args.no_temperature,
                temperature_sensor_type=args.temperature_sensor_type,
                temperature_debug=args.temperature_debug,
            )
        else:
            selected_workout_type = choose_workout_type(args.workout)
            if args.mqtt:
                run_mqtt_mode(
                    workout_type=selected_workout_type,
                    session_id=args.session_id,
                    random_seed=args.seed,
                    interval_seconds=args.interval,
                    decisions=args.decisions,
                )
            else:
                run_forever(
                    workout_type=selected_workout_type,
                    session_id=args.session_id,
                    random_seed=args.seed,
                    interval_seconds=args.interval,
                    decisions=args.decisions,
                )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
