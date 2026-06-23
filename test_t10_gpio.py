import time
import RPi.GPIO as GPIO

PIN = 3  # candidate shutdown pin, has built-in pull-up

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print(f"Watching GPIO{PIN}. Press the button a few times (Ctrl+C to stop).")
print("Reports press duration; >1.5s flagged as 'long press'.")

last_state = GPIO.input(PIN)
press_start = None
try:
    while True:
        state = GPIO.input(PIN)
        if state == 0 and last_state == 1:
            press_start = time.time()
        elif state == 1 and last_state == 0 and press_start:
            dur = time.time() - press_start
            kind = "LONG" if dur > 1.5 else "short"
            print(f"press detected: {dur:.2f}s ({kind})")
            press_start = None
        last_state = state
        time.sleep(0.02)
except KeyboardInterrupt:
    GPIO.cleanup()
    print("done")
