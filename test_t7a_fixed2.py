import time
import numpy as np
from picamera2 import Picamera2

WIDTH = 2592
CROP_HEIGHT = 200
CENTER_Y = 205
BAND_HALF_HEIGHT = 27
EXPOSURES_US = [20000, 50000, 100000, 200000]
CLIP_THRESHOLD = 254.0

def to_grey(f):
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    return 0.299 * r + 0.587 * g + 0.114 * b

def band_slice(g):
    return g[CENTER_Y - BAND_HALF_HEIGHT: CENTER_Y + BAND_HALF_HEIGHT, :]

def main():
    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration(main={"size": (WIDTH, CROP_HEIGHT), "format": "RGB888"}))
    picam2.start()
    picam2.set_controls({"AeEnable": False, "AwbEnable": False, "AnalogueGain": 1.0})
    time.sleep(0.5)

    print(f"{'exp_us':>9} | {'max':>6} | {'mean':>6} | {'clip%':>6} | actual_exp | flag")
    for exp in EXPOSURES_US:
        picam2.set_controls({"ExposureTime": exp, "FrameDurationLimits": (exp, 3200000)})
        settle = max(0.3, (exp / 1e6) * 3)
        time.sleep(settle)
        picam2.capture_array("main")  # discard stale frame
        time.sleep(settle)
        frame = picam2.capture_array("main").astype(np.float32)
        meta = picam2.capture_metadata()
        band = band_slice(to_grey(frame))
        mx, mn, cf = float(band.max()), float(band.mean()), float(np.mean(band >= CLIP_THRESHOLD) * 100)
        flag = "** SATURATED **" if mx >= 255 else ("near-clip" if cf > 0.5 else "")
        print(f"{exp:>9} | {mx:6.1f} | {mn:6.1f} | {cf:6.2f} | {meta.get('ExposureTime'):>10} | {flag}")
    picam2.stop()

if __name__ == "__main__":
    main()
