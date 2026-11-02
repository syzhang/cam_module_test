"""Native Windows baseline: stream the module's raw UVC interfaces without the vendor SDK.

Run on Windows (not WSL) while the camera is NOT attached to WSL:
    python native_baseline.py [seconds] [output_dir]

Probes DirectShow camera indices, picks the ones whose frame size matches the module's
UVC formats (RGB 1280x1280, fisheye 640x1922, ToF 640x482), records frame arrival times
for each, saves a sample frame, and writes <out>/native_<name>.csv for analyze.py.
"""
import csv
import os
import sys
import time

import cv2

KNOWN = {(1280, 1280): "rgb", (640, 1922): "fisheye", (640, 482): "tof"}
duration = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
out_dir = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "native"))
os.makedirs(out_dir, exist_ok=True)


def probe(max_index=10):
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # Try each module format in case the driver opened at a different default size.
        name = KNOWN.get((w, h))
        if name is None:
            for (kw, kh), kname in KNOWN.items():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, kw)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, kh)
                if (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))) == (kw, kh):
                    name, w, h = kname, kw, kh
                    break
        print("index %d: %dx%d fps=%.0f -> %s" % (idx, w, h, cap.get(cv2.CAP_PROP_FPS), name or "other camera"))
        cap.release()
        if name:
            found.append((idx, name, w, h))
    return found


def measure(idx, name, w, h):
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    if name == "rgb":
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    for _ in range(5):  # let exposure / stream settle
        cap.read()
    rows, sample, failures = [], None, 0
    start = time.perf_counter()
    while time.perf_counter() - start < duration:
        ok, frame = cap.read()
        t = time.perf_counter() - start
        if not ok:
            failures += 1
            continue
        rows.append((len(rows), t))
        if sample is None:
            sample = frame
    cap.release()
    path = os.path.join(out_dir, "native_%s.csv" % name)
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["frame", "arrival_s"])
        wr.writerows(rows)
    if sample is not None:
        cv2.imwrite(os.path.join(out_dir, "native_%s.png" % name), sample)
    fps = len(rows) / duration
    print("%-8s idx=%d %dx%d  %d frames in %.0fs = %.1f fps  (read failures: %d)  shape=%s"
          % (name, idx, w, h, len(rows), duration, fps, failures, None if sample is None else sample.shape))


cams = probe()
if not cams:
    print("No module UVC interfaces found. Is the camera detached from WSL (usbipd detach --busid 1-5)?")
    sys.exit(1)
for cam in cams:
    measure(*cam)
print("saved to", out_dir)
