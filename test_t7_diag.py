import time
from picamera2 import Picamera2

picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": (2592, 200), "format": "RGB888"}))
picam2.start()
picam2.set_controls({"AeEnable": False, "AwbEnable": False, "AnalogueGain": 1.0,
                      "FrameDurationLimits": (100, 3200000)})
time.sleep(0.5)

print("Mode's allowed FrameDurationLimits:", picam2.camera_controls["FrameDurationLimits"])
print("Mode's allowed ExposureTime range:", picam2.camera_controls["ExposureTime"])
print()

for exp in [20000, 50000, 100000, 200000]:
    picam2.set_controls({"ExposureTime": exp})
    time.sleep(0.3)
    picam2.capture_array("main")
    meta = picam2.capture_metadata()
    print(f"requested={exp:>7}  actual_ExposureTime={meta.get('ExposureTime')}  actual_FrameDuration={meta.get('FrameDuration')}")

picam2.stop()
