import time
import numpy as np
from picamera2 import Picamera2

CENTER_Y, BH = 205, 27
N_FRAMES = 10

def to_grey(f):
    return 0.299*f[...,0] + 0.587*f[...,1] + 0.114*f[...,2]

picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": (2592, 200), "format": "RGB888"}))
picam2.start()
picam2.set_controls({"AeEnable": False, "AwbEnable": False, "AnalogueGain": 1.0})
time.sleep(1)

chosen = None
for exp in [200, 500, 1000, 2000, 5000, 10000, 20000]:
    picam2.set_controls({"ExposureTime": exp, "FrameDurationLimits": (exp, 3200000)})
    time.sleep(0.3)
    f = picam2.capture_array("main").astype(np.float32)
    band = to_grey(f)[CENTER_Y-BH:CENTER_Y+BH, :]
    print(f"exp={exp:>6} max={band.max():.1f} mean={band.mean():.1f}")
    if band.max() < 250:
        chosen = exp
        break

if chosen is None:
    print("Still saturated at 20000us — dim the light more.")
else:
    print(f"\nUsing exp={chosen}, capturing {N_FRAMES} frames...")
    profiles = []
    for _ in range(N_FRAMES):
        f = picam2.capture_array("main").astype(np.float32)
        profiles.append(to_grey(f)[CENTER_Y-BH:CENTER_Y+BH, :].mean(axis=0))
    profile = np.mean(profiles, axis=0)
    norm = profile / profile.mean()
    print(f"mean={profile.mean():.2f} min={profile.min():.2f} max={profile.max():.2f}")
    print(f"normalized range: {norm.min():.3f} - {norm.max():.3f}")
    for i in range(0, 2592, 259):
        print(f"col {i:>5}: {profile[i]:.2f}")

picam2.stop()
