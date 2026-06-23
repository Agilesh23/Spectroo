import time
import numpy as np
from picamera2 import Picamera2

CENTER_Y, BH = 205, 27
DURATION_S = 300
INTERVAL_S = 10

def to_grey(f):
    return 0.299*f[...,0] + 0.587*f[...,1] + 0.114*f[...,2]

picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": (2592, 200), "format": "RGB888"}))
picam2.start()
picam2.set_controls({"AeEnable": False, "AwbEnable": False, "AnalogueGain": 1.0,
                      "ExposureTime": 200000, "FrameDurationLimits": (200000, 3200000)})
time.sleep(1)

print("LENS MUST BE CAPPED. Starting dark drift capture...")
print(f"{'t_s':>6} | {'mean':>7} | {'max':>7}")

t0 = time.time()
while time.time() - t0 < DURATION_S:
    f = picam2.capture_array("main").astype(np.float32)
    band = to_grey(f)[CENTER_Y-BH:CENTER_Y+BH, :]
    print(f"{time.time()-t0:6.0f} | {band.mean():7.3f} | {band.max():7.1f}")
    time.sleep(INTERVAL_S)

picam2.stop()
