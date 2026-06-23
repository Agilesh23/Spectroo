import time
import threading
from picamera2 import Picamera2

picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": (2592, 200), "format": "RGB888"}))
picam2.start()
time.sleep(0.5)

errors = []
counts = {"main": 0, "second": 0}

def loop(name, interval):
    while not stop_flag.is_set():
        try:
            picam2.capture_array("main")
            counts[name] += 1
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {e}")
        time.sleep(interval)

stop_flag = threading.Event()
t1 = threading.Thread(target=loop, args=("main", 0.05))    # simulates desktop UI live timer
t2 = threading.Thread(target=loop, args=("second", 0.08))  # simulates web stream / dev dialog timer
t1.start()
t2.start()

print("Running two concurrent capture loops for 20s (simulating UI + web server)...")
time.sleep(20)
stop_flag.set()
t1.join()
t2.join()
picam2.stop()

print(f"main loop captures: {counts['main']}")
print(f"second loop captures: {counts['second']}")
print(f"errors: {len(errors)}")
for e in errors[:10]:
    print(" -", e)
