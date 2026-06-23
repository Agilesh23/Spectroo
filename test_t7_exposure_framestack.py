import time
import numpy as np
from picamera2 import Picamera2

WIDTH = 2592
CROP_HEIGHT = 200
CENTER_Y = 205
BAND_HALF_HEIGHT = 27
EXPOSURES_US = [20000, 50000, 100000, 200000]
FRAME_STACK_CANDIDATES = [1, 2, 4, 8]
STACK_CHECK_EXPOSURE_US = 200000
POOL_SIZE = max(FRAME_STACK_CANDIDATES) * 4
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

    print("T7a — exposure sweep")
    print(f"{'exp_us':>9} | {'max':>6} | {'mean':>6} | {'clip%':>6} | flag")
    for exp in EXPOSURES_US:
        picam2.set_controls({"ExposureTime": exp})
        time.sleep(0.3)
        band = band_slice(to_grey(picam2.capture_array("main").astype(np.float32)))
        mx, mn, cf = float(band.max()), float(band.mean()), float(np.mean(band >= CLIP_THRESHOLD) * 100)
        flag = "** SATURATED **" if mx >= 255 else ("near-clip" if cf > 0.5 else "")
        print(f"{exp:>9} | {mx:6.1f} | {mn:6.1f} | {cf:6.2f} | {flag}")

    print(f"\nT7b — frame-stack noise check @ {STACK_CHECK_EXPOSURE_US}us")
    picam2.set_controls({"ExposureTime": STACK_CHECK_EXPOSURE_US})
    time.sleep(0.3)
    pool = np.array([band_slice(to_grey(picam2.capture_array("main").astype(np.float32))).mean(axis=0)
                      for _ in range(POOL_SIZE)])
    prev = None
    print(f"{'stack':>5} | {'noise_std':>10} | delta")
    for n in FRAME_STACK_CANDIDATES:
        groups = POOL_SIZE // n
        stacks = np.array([pool[i*n:(i+1)*n].mean(axis=0) for i in range(groups)])
        std = float(stacks.std(axis=0).mean())
        print(f"{n:>5} | {std:10.4f} | {'' if prev is None else f'{std-prev:+.4f}'}")
        prev = std
    picam2.stop()

if __name__ == "__main__":
    main()
