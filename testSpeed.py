"""Quick manual speed Hall sensor test.

Run this on the Raspberry Pi when you want to confirm the wheel magnet and D3
Hall sensor are producing believable speed readings.
"""

import time
from collections import deque
import grovepi

# Change this if your speed Hall sensor is on another port
SPEED_PIN = 3

# Your old output suggests you used around 2.09m to 2.10m
# Adjust this based on your wheel circumference
WHEEL_CIRCUMFERENCE_M = 2.09

# 1 magnet on the wheel = 1 pulse per wheel rotation
# 2 magnets = 2
PULSES_PER_REVOLUTION = 1

# Most Hall modules are HIGH normally and LOW when magnet is detected
MAGNET_DETECTED_STATE = 0

# Ignore very fast duplicate triggers/noise
DEBOUNCE_SECONDS = 0.04

# After this many seconds without a pulse, speed becomes 0
STOP_TIMEOUT_SECONDS = 3.0

# Average the last few pulse-based speed readings
AVERAGE_WINDOW = 5

POLL_DELAY_SECONDS = 0.003

# Configure the GrovePi pin before the polling loop starts.
grovepi.pinMode(SPEED_PIN, "INPUT")

# These values track edge timing between magnet detections.
last_state = grovepi.digitalRead(SPEED_PIN)
last_pulse_time = None
last_valid_pulse_time = None
speed_samples = deque(maxlen=AVERAGE_WINDOW)

last_print_time = time.monotonic()

print("Accurate speed test started.")
print("Move the magnet slowly first, then spin the wheel.")
print("Press CTRL+C to stop.\n")

try:
    while True:
        now = time.monotonic()
        state = grovepi.digitalRead(SPEED_PIN)

        # Detect transition into magnet-detected state
        if last_state != MAGNET_DETECTED_STATE and state == MAGNET_DETECTED_STATE:
            if (
                last_valid_pulse_time is None
                or (now - last_valid_pulse_time) >= DEBOUNCE_SECONDS
            ):
                if last_pulse_time is not None:
                    # Time between pulses gives rotations; circumference gives distance.
                    interval = now - last_pulse_time

                    instant_speed_kmh = (
                        WHEEL_CIRCUMFERENCE_M / (interval * PULSES_PER_REVOLUTION)
                    ) * 3.6

                    speed_samples.append(instant_speed_kmh)
                    # A short rolling average makes the printed value less jumpy.
                    avg_speed_kmh = sum(speed_samples) / len(speed_samples)

                    print(
                        f"Pulse | interval={interval:.3f}s | "
                        f"instant={instant_speed_kmh:.2f} km/h | "
                        f"average={avg_speed_kmh:.2f} km/h"
                    )
                else:
                    print(
                        "First pulse detected. Waiting for next pulse to calculate speed."
                    )

                last_pulse_time = now
                last_valid_pulse_time = now

        last_state = state

        # Print 0 only if the wheel really stopped for a few seconds
        if (
            last_pulse_time is not None
            and (now - last_pulse_time) > STOP_TIMEOUT_SECONDS
        ):
            if speed_samples:
                print("No pulse recently. Speed: 0.00 km/h")
                # Clear the average so the next spin starts fresh.
                speed_samples.clear()
            last_pulse_time = None

        time.sleep(POLL_DELAY_SECONDS)

except KeyboardInterrupt:
    print("\nStopped speed test.")
