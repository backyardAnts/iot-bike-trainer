import grovepi
import time

SPEED_PIN = 3
WHEEL_CIRCUMFERENCE_M = 2.1  # adjust based on your wheel size
PULSES_PER_REV = 1  # change to 2 if you use 2 magnets

grovepi.pinMode(SPEED_PIN, "INPUT")

pulse_count = 0
last_state = 1
last_pulse_time = 0
start_time = time.time()

DEBOUNCE_TIME = 0.05  # 50 ms

while True:
    try:
        state = grovepi.digitalRead(SPEED_PIN)
        now = time.time()

        # Detect falling edge: magnet detected
        if last_state == 1 and state == 0:
            if now - last_pulse_time > DEBOUNCE_TIME:
                pulse_count += 1
                last_pulse_time = now
                print("Pulse detected:", pulse_count)

        last_state = state

        elapsed = now - start_time

        if elapsed >= 2:
            wheel_revs = pulse_count / PULSES_PER_REV
            speed_kmh = (wheel_revs * WHEEL_CIRCUMFERENCE_M / elapsed) * 3.6

            print("Speed:", round(speed_kmh, 2), "km/h")

            pulse_count = 0
            start_time = now

        time.sleep(0.005)

    except KeyboardInterrupt:
        break
    except Exception as e:
        print("Error:", e)
        time.sleep(0.1)
