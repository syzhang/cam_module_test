"""Headless smoke test for the camera module via the vendor SDK's C interface.

Starts IMU, stereo fisheye and RGB (optionally ToF) streams, counts unique frames for a
few seconds, prints rates, and saves one image from each camera.

Usage: python3 smoke_test.py [seconds] [output_dir]   (normally run via scripts/test_streams.sh)
Set STREAMS=imu,stereo,rgb,tof to choose streams (default imu,stereo,rgb); TOF=1 adds tof.

Frames are fetched through fixed, oversized buffers rather than the SDK wrapper's stock getters:
those size the buffer from a separate *_info() call, and a frame arriving between the two
calls overflows it and corrupts the Python heap (segfault in PyObject_Malloc).
"""
import os
import sys
import time
from ctypes import byref, c_double, c_int, c_longlong, c_ubyte

import cv2
import numpy as np

WRAPPER_DIR = "/usr/share/python-wrapper"
BUF_SIZE = 32 * 1024 * 1024  # far above any frame this module produces
duration = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
out_dir = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__)))
STREAMS = set(os.environ.get("STREAMS", "imu,stereo,rgb").split(","))
if os.environ.get("TOF", "0") == "1":
    STREAMS.add("tof")
USE_TOF = "tof" in STREAMS

# The wrapper loads its library with a path relative to the wrapper directory.
os.chdir(WRAPPER_DIR)
sys.path.insert(0, WRAPPER_DIR)
import xvsdk  # noqa: E402

dll = xvsdk.dll
buf_a = (c_ubyte * BUF_SIZE)()
buf_b = (c_ubyte * BUF_SIZE)()
width, height, size, codec = c_int(), c_int(), c_int(), c_int()
edge_ts, host_ts = c_longlong(), c_double()


def as_array(buf, n):
    return np.ctypeslib.as_array(buf)[:n].copy()


def get_stereo():
    dll.xv_get_stereo_info(byref(width), byref(height), byref(edge_ts), byref(host_ts), byref(size))
    if size.value <= 0:
        return None
    dll.xv_get_stereo_image(byref(buf_a), byref(buf_b))
    n = width.value * height.value
    return width.value, height.value, edge_ts.value, as_array(buf_a, n), as_array(buf_b, n)


def get_rgb():
    dll.xv_get_rgb_info(byref(width), byref(height), byref(edge_ts), byref(host_ts), byref(size), byref(codec))
    if size.value <= 0:
        return None
    dll.xv_get_rgb_image(byref(buf_a))
    return width.value, height.value, edge_ts.value, codec.value, as_array(buf_a, min(size.value, BUF_SIZE))


def get_tof():
    dll.xv_get_tof_info(byref(width), byref(height), byref(edge_ts), byref(host_ts), byref(size), byref(codec))
    if size.value <= 0:
        return None
    dll.xv_get_tof_image(byref(buf_a))
    return width.value, height.value, edge_ts.value, codec.value, as_array(buf_a, min(size.value, BUF_SIZE))


def decode_rgb(w, h, data):
    if data.size >= w * h * 3 // 2 and data[:2].tolist() != [0xFF, 0xD8]:
        yuv = data[: w * h * 3 // 2].reshape(h * 3 // 2, w)
        return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_IYUV)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)  # MJPEG frame


print("init:", xvsdk.init())
print("streams:", ",".join(sorted(STREAMS)))
if "imu" in STREAMS:
    xvsdk.imu_start()
if "stereo" in STREAMS:
    xvsdk.stereo_start()
if "rgb" in STREAMS:
    xvsdk.rgb_start()
if USE_TOF:
    xvsdk.tof_start()

seen = {"imu": set(), "stereo": set(), "rgb": set(), "tof": set()}
saved = set()
last_imu = None
start = time.time()

while time.time() - start < duration:
    accel, gyro, imu_edge, _ = xvsdk.xslam_get_imu()
    if imu_edge.value:
        seen["imu"].add(imu_edge.value)
        last_imu = (accel.x, accel.y, accel.z, gyro.x, gyro.y, gyro.z)

    frame = get_stereo() if "stereo" in STREAMS else None
    if frame:
        w, h, ts, left, right = frame
        seen["stereo"].add(ts)
        if "stereo" not in saved:
            cv2.imwrite(os.path.join(out_dir, "fisheye_left.png"), left.reshape(h, w))
            cv2.imwrite(os.path.join(out_dir, "fisheye_right.png"), right.reshape(h, w))
            print("fisheye: %dx%d" % (w, h))
            saved.add("stereo")

    frame = get_rgb() if "rgb" in STREAMS else None
    if frame:
        w, h, ts, rgb_codec, data = frame
        seen["rgb"].add(ts)
        if "rgb" not in saved:
            img = decode_rgb(w, h, data)
            print("rgb: %dx%d codec=%d bytes=%d decoded=%s" % (w, h, rgb_codec, data.size, img is not None))
            if img is not None:
                cv2.imwrite(os.path.join(out_dir, "rgb.png"), img)
            saved.add("rgb")

    if USE_TOF:
        frame = get_tof()
        if frame:
            w, h, ts, tof_type, data = frame
            seen["tof"].add(ts)
            if "tof" not in saved:
                n = w * h
                # Depth is float32 or uint16 depending on module; infer from buffer size.
                dtype = np.float32 if data.size >= n * 4 else np.uint16
                depth = np.nan_to_num(data[: n * np.dtype(dtype).itemsize].view(dtype).reshape(h, w).astype(np.float32))
                vis = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                cv2.imwrite(os.path.join(out_dir, "tof_depth.png"), cv2.applyColorMap(vis, cv2.COLORMAP_JET))
                print("tof: %dx%d type=%d bytes=%d range=%.3f..%.3f"
                      % (w, h, tof_type, data.size, depth.min(), depth.max()))
                saved.add("tof")

    time.sleep(0.002)

elapsed = time.time() - start
print("\n--- %.1fs ---" % elapsed)
for name, stamps in seen.items():
    if name in STREAMS:
        print("%-7s %5d unique samples  ~%.1f Hz" % (name, len(stamps), len(stamps) / elapsed))
if last_imu:
    print("last imu accel=(%.2f, %.2f, %.2f) gyro=(%.3f, %.3f, %.3f)" % last_imu)
print("images saved to", out_dir)

xvsdk.stop()
os._exit(0)
