# Camera module: test summary (2026-11-02)

## 1. Setup

| | |
|---|---|
| Module | vendor camera module (4 fisheye, IMU, RGB, ToF); serial number and firmware details redacted (pre-release firmware build) |
| Sensors exposed | 4× fisheye 640×480 grayscale (2 stereo pairs), IMU, RGB 1280×1280 MJPEG, ToF 640×482 (disabled in module config) |
| Host | Surface laptop, Windows 11, USB 3 (5 Gbps) |
| Linux | WSL2 Ubuntu 24.04 (kernel 5.15), camera passed through with usbipd-win 5.3.0 (USB/IP) |
| SDK | vendor SDK 3.2.0 (a .deb built for Ubuntu 20.04; installs fine on 24.04) |

## 2. How it was tested

1. **Install**: SDK deps + `.deb` + udev rule in WSL; usbipd-win on Windows; camera bound and attached to WSL.
2. **Smoke test** (`smoke_test.py`): start each stream through the SDK's Python wrapper, count frames, save a sample.
   Found and worked around a bug in the stock wrapper (the wrapper sizes frame buffers from a separate info call;
   a frame arriving in between overflows the buffer and crashes Python).
3. **Per-stream isolation** (`test_each_stream.sh`): IMU / stereo / RGB / ToF one at a time.
4. **Vendor demos** (`build_c_demos.sh`, `run_c_demos.sh`): built the SDK's C++ stream demo and
   its C-interface demo to check whether the RGB crash is ours or the SDK's.
5. **Native Windows baseline attempt** (`native_baseline.py`): the module's UVC interfaces open on Windows but send
   no frames without the vendor SDK (no Windows SDK in this package), so no native comparison was possible.
6. **Recorder** (`recorder/cam_recorder.cpp`): C++ tool using SDK callbacks; logs every IMU sample, every fisheye frame
   (all 4 images as PGM) and optional SLAM pose, each with three clocks: camera time, SDK host time, actual arrival.
7. **Recordings**: 3× 30 s (streams only / +saving images / +SLAM), 1 min static, 1 min hand-held motion.
8. **Analysis**:
   - `analyze.py`: delivery per stream: received vs nominal rate, loss (gaps on the camera's own clock), latency, jitter.
   - `image_metrics.py`: per frame: exposure, clipping, sharpness, temporal noise, feature-tracked image motion.
   - `module_quality.py`: sensor quality: IMU noise/bias/Allan deviation, gravity consistency, camera-IMU time
     alignment, motion blur, clock drift. Output in `quality_report/`.

## 3. What works

| stream | status |
|---|---|
| IMU | ✅ works in WSL, with heavy sample loss |
| 4× fisheye (hardware-synced) | ✅ works in WSL, with heavy frame loss and ~0.25–0.3 s delay |
| SLAM pose (SDK, host mode) | ⚠️ worked once (~156 Hz); later runs gave no IMU/pose; the module hung soon after one of them and had to be replugged |
| RGB 1280×1280 MJPEG | ❌ segfault in the SDK's video library (memcpy overflow while assembling a frame) in Python **and** in the vendor's C/C++ demos |
| ToF / RGB-D | ❌ disabled in the module's own config (`"tof":{"en":0}`); no frames |

The module hung twice during the day (Windows: "Set Address Failed" / disappeared) and needed a replug.

## 4. Effect of WSL (USB/IP) on the streams

Measured against the camera's own timestamps, so loss is counted exactly:

| session | IMU received / nominal | IMU loss | fisheye received / 30 fps | fisheye loss | fisheye latency median (max) |
|---|---|---|---|---|---|
| 30 s, streams only | 148 / ~500 Hz | 71% | 11.4 fps | 62% | 297 ms (333) |
| 30 s, + saving images | 145 / ~500 Hz | 71% | 11.2 fps | 63% | 302 ms (350) |
| 1 min static | 155 / ~500 Hz | 69% | 11.4 fps | 62% | 297 ms (341) |
| 1 min motion (with live preview) | 277 / ~500 Hz | 45% | 14.4 fps | 52% | 236 ms (285) |

- The camera captures on a clean 30 fps grid; received frames are exactly 2 or 3 frame periods apart, so frames
  are captured but lost in transport, not skipped by the camera.
- IMU timestamps sit on a 2 ms grid (≈500 Hz sensor); the host gets 30–55% of samples.
- Disk writes are not the cause (saving every image changed nothing). Loss varies 45–71% between runs.
- One corrupted fisheye timestamp (3.6×10¹⁷ µs) in 1 min, plus `vhci_hcd: urb->status -104` resets in the kernel log.
- **Verdict on WSL:** fine for seeing that the module works and for checking per-sample sensor quality;
  **not usable for real data collection** (missing data, 0.3 s delay, instability, no RGB).

## 5. Module quality (what the saved data can tell despite WSL)

Dropped samples reduce *how much* data there is, not *what each sample says*, and everything below uses the camera's
own clock. So these numbers describe the sensors, with the caveats noted.

**IMU (static, 60 s)**

| | x | y | z |
|---|---|---|---|
| accel noise | 1.9 mg | 1.7 mg | 1.5 mg |
| accel noise density* | 117 µg/√Hz | 107 µg/√Hz | 97 µg/√Hz |
| gyro bias | +0.31 °/s | +0.66 °/s | +0.43 °/s |
| gyro noise | 0.16 °/s | 0.43 °/s | 0.13 °/s |
| gyro noise density* | 0.010 °/s/√Hz | 0.027 °/s/√Hz | 0.008 °/s/√Hz |
| gyro bias instability (60 s Allan min, rough) | 50 °/h | 139 °/h | 25 °/h |

\* assumes the 500 Hz output rate is the noise bandwidth.

- Gravity reads 9.778 m/s² (−0.3% vs 9.807): good scale/offset for an uncalibrated read.
- Accel and gyro x/z noise are in the normal range for consumer MEMS IMUs used in VIO. **The gyro y-axis is ~3× noisier**
  than x/z in every metric. It could be that axis or vibration from the table/laptop fan; worth re-checking on a
  different surface.
- The gyro has a constant bias of 0.3–0.7 °/s; uncorrected it drifts 20–40°/min. That is normal and SLAM estimates it,
  but it means "the IMU changes when still" is just noise + bias.
- In motion: peaks of 270 °/s and 1.6 g with no saturation. Propagating gravity with the gyro across the 1-min hand-held
  run (despite 45% of samples missing) stays within ~4–10° of the accelerometer: no runaway error.

**Fisheye cameras**

| cam | mean level | clipped (≥250) | black (≤5) | temporal noise |
|---|---|---|---|---|
| 0 | 63 | 7.5% | 0.5% | 1.75 DN |
| 1 | 63 | 7.4% | 0.3% | 1.67 DN |
| 2 | 71 | 5.8% | 5.4% | 1.98 DN |
| 3 | 48 | 1.8% | 2.6% | 1.64 DN |

- Low noise (≈1.7–2 DN of 255). Exposure is driven by the room; bright windows clip to white (no HDR), so 2–8% of
  pixels are saturated in this backlit room.
- Cams 2/3 have dark corners (vignetting of the wider-angle pair).
- **No measurable motion blur**: sharpness relative to neighbouring frames stays at 1.00 from 0 to >200 °/s, and the fastest
  frame (270 °/s) is visibly sharp on inspection (image not included in this repo). Global shutter plus short exposure; good for VIO.
- All 4 images in a frame share one timestamp (hardware sync).

**Timing**

- **Camera–IMU alignment: 0 ms offset (±10 ms resolution)**, correlation 0.95 between gyro rate and image motion on both
  camera pairs (`quality_report/sync.png`). Timestamps are consistent across sensors, which matters most for VIO.
- Camera clock drifts ~50 ppm vs the host clock; the SDK handles the mapping.

## 5b. 10-minute guided test (`data/20261102_081710_protocol/protocol_analysis/`)

17 timed steps (rests, slow/fast pitch/yaw/roll, translations, 2.5 min walking, mixed fast motion).
**The camera linked at USB 2.0 (480 Mbps) this time, and the fisheye cameras sent no frames at all for 10 minutes;
the IMU kept working.** There was no error from the SDK, just silence. So this run is IMU-only; image–IMU checks need a
re-run with a USB 3 link.

- **IMU delivery at USB 2.0, no video traffic: 37% loss (≈310 Hz received)** across all steps, still or moving, vs
  45–71% with video at USB 3. So part of the IMU loss is the video sharing the USB/IP link.
- **Bias stability over 10 min (6 rest periods):** gyro bias spread 0.12 / 0.37 / 0.09 °/s (x/y/z). x/z are stable; y drifts
  most (−0.17 → +0.20 °/s), mainly in the first 3 minutes (warm-up?). Gravity magnitude 9.766–9.793 m/s² (±0.15%). Noise the
  same in every rest (gyro y again ~3× noisier).
- **The IMU reports no temperature** (`temperature` = 0 K in every sample), so bias can't be modelled against temperature.
- **No saturation** at 662 °/s and 4.4 g peaks.
- **Axis mapping:** pitch (nod) → gyro x, yaw (turn) → gyro y, roll → z.
- **Gyro integration over 10 min** (gravity predicted by the gyro vs accelerometer at each rest): 2° after the slow
  rotations, then +29° during the fast rotations, 70° after 10 min. Thinning the samples further and extrapolating to
  0% loss gives **≈13° from the gyro itself and ≈68% of the error from dropped samples**. Expect much better with a
  lossless link. The remaining part (bias change and scale error at high rates) should be re-measured natively.

## 5c. 10-minute guided test on USB 3: 7 minutes recorded (`data/20261102_084425_protocol/protocol_analysis/`)

Same protocol, USB 3 link, images + IMU. **The module dropped off USB at 425 s** (`vhci_hcd: connection reset by peer`,
5th failure of the day), so the end of the walk, the last rest and the mixed-fast step are missing. Covered: 4 rests,
slow rotations, fast rotations, translations, 90 s of walking.

- **Delivery:** IMU 194 Hz (62% loss), fisheye 12.3 fps (59% loss), fisheye latency 277 ms median (p99 328 ms).
  Loss barely changes between still and moving. **7 corrupted fisheye timestamps** in 7 min (single bad frames).
  IMU loss is 62% here vs 37% in the USB 2 IMU-only run: the video traffic costs IMU samples.
- **Image–IMU time alignment: +1 ms over the whole run (corr 0.98, cam 0)**; per motion block −2…+6 ms;
  43 sliding 30-s windows: mean +1.4 ms, std 4.1 ms, range −11…+10 ms, **no drift over 7 minutes**
  (`sync_over_time.png`). Both camera pairs agree. Resolution is limited by the ~12 fps delivered here.
- **Motion blur:** none up to 300 °/s (relative sharpness 1.00); 0.94 above 300 °/s (64 frames). Global shutter holds up.
- **Image motion vs rotation:** feature tracking works throughout (140–210 tracked points per frame even in the fast block),
  so the images remain usable for VIO at these speeds.
- **IMU bias over 7 min (4 rests):** spread 0.07 / 0.16 / 0.05 °/s (x/y/z); y again moves most, others very stable.
  Noise identical in every rest; |g| 9.780–9.783 m/s² (±0.02%).
- **Gyro integration:** 1° after the slow block, then +36° during the fast-rotation block, 45° after 5 min. Thinning
  the samples further and extrapolating to 0% loss gives ~0°: the drift here is **essentially all from dropped samples**
  (the earlier USB 2 run gave ≈13° intrinsic; together: the gyro itself contributes 0–13° over 5–10 min of hard motion, the
  drops contribute the rest).
- **Axis mapping:** pitch → x, yaw → y (clean single-axis windows 82% / 76%); roll → z was never performed cleanly
  (best 49%).

## 6. How far to trust this

| reliable from these tests | not reliable / not measured |
|---|---|
| per-sample IMU noise, bias, gravity scale | true delivered rates and latency on native Linux |
| fisheye noise, exposure, blur, sync between the 4 cameras | IMU bias stability over minutes to hours (needs ≥1 h static) |
| camera–IMU time alignment | SLAM accuracy (SLAM unreliable here, and would suffer from the drops) |
| that frames are captured at 30 fps and lost in transport | RGB and ToF/RGB-D quality (not streamable) |
| | calibration quality (intrinsics/extrinsics not checked) |

**Overall:** the parts we could test look healthy for a VIO/UMI module: low image noise, no motion blur, hardware-synced
cameras, IMU and camera time-aligned, IMU noise in the normal range apart from the noisier gyro y-axis. The serious problems
seen here come from **WSL USB passthrough** (drops, latency, hangs) and the **SDK** (RGB crash), not clearly from the hardware.

## 7. Next steps

1. Repeat on **native Ubuntu 20.04** with the same tools (`recorder/`, `analyze.py`, `module_quality.py`); expect ~0% loss,
   30 fps and low latency if the hardware is fine. This is the real acceptance test.
2. Report the RGB crash to the vendor with the backtrace and the RGB configuration, and ask for an SDK build
   that matches the firmware.
3. Ask how to enable ToF in the module config if RGB-D is needed.
4. Record ≥1 h static on a still, vibration-free surface for proper IMU Allan deviation; re-check gyro y.
5. Test SLAM on native Linux; check calibration (intrinsics/extrinsics) against a checkerboard.

## Files

`USAGE.md` (commands) · `data/<session>/` (CSVs + `analysis/report.md`, plots, `image_metrics.csv`) ·
`quality_report/quality.md` (+ `allan.png`, `imu_motion.png`, `sync.png`) ·
images for each session in the WSL data folder (`<session>/fisheye/`).
