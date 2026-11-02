# Module quality assessment

Still session: `20261102_1min`  
Motion session: `20261102_075328_motion`

## IMU at rest

| | x | y | z |
|---|---|---|---|
| accel mean (m/s²) | +1.163 | -9.562 | -1.676 |
| accel noise std (m/s²) | 0.0181 | 0.0166 | 0.0151 |
| accel noise (mg) | 1.85 | 1.69 | 1.54 |
| gyro bias (°/s) | +0.309 | +0.660 | +0.433 |
| gyro noise std (°/s) | 0.157 | 0.426 | 0.129 |
| gyro noise density (°/s/√Hz, assuming 500 Hz ODR) | 0.0099 | 0.0269 | 0.0081 |
| accel noise density (µg/√Hz) | 117 | 107 | 97 |

- Gravity magnitude: **9.7777 m/s²** (std 0.0166), vs standard 9.80665: -0.30%.
- Tilt from gravity direction: 12.0° off the -y axis.
- Uncorrected gyro bias would drift heading by 19°/40°/26° per minute (x/y/z).

- Gyro bias instability (Allan minimum, only 60 s of data so a rough lower bound): 49.7 / 138.9 / 25.0 °/h (x/y/z). See `allan.png`.

## IMU in motion

- Peak angular rate: 269 / 197 / 167 °/s (x/y/z); peak |accel| 16.0 m/s² (1.6 g).
- No values sit at a constant rail, so no sign of saturation at these motion levels.
- The camera was moving for the whole recording (|gyro| never below ~20°/s), so there is no rest period here; the bias from the still session is used instead.
- Rotation that happened inside transport gaps (estimated): 2359° in total, i.e. the gyro has to be integrated across 45% of the elapsed time without samples.

Gravity-consistency check (angle between gyro-propagated gravity and the accelerometer, at moments with |a| within 0.3 m/s² of g):

| gyro | after 10 s | after 30 s | after 60 s | median |
|---|---|---|---|---|
| raw | 3.8° | 6.7° | 9.6° | 6.1° |
| bias-corrected (still-session bias) | 5.6° | 7.4° | 3.9° | 5.9° |

A few degrees of disagreement is expected from linear acceleration while moving by hand. Steady growth means rotation is being lost or mis-scaled.

## Device clock

- Drift of the camera clock relative to the host: 49 ppm (still), 56 ppm (motion).
  (from the minimum-latency envelope of IMU arrivals; the SDK maps device time to host time, so a few hundred ppm is harmless for recording.)
- All 4 fisheye images in a frame carry one device timestamp: the cameras are hardware-synchronised.

## Fisheye cameras (640×480 each, 4 cameras, global shutter, grayscale)

| cam | mean level (0–255) | saturated px % | black px % | sharpness still | sharpness motion | temporal noise (DN) |
|---|---|---|---|---|---|---|
| 0 | 63 | 7.49 | 0.51 | 576 | 175 (min 35) | 1.75 |
| 1 | 63 | 7.38 | 0.25 | 311 | 180 (min 36) | 1.67 |
| 2 | 71 | 5.83 | 5.42 | 84 | 197 (min 94) | 1.98 |
| 3 | 48 | 1.75 | 2.57 | 56 | 150 (min 79) | 1.64 |

- Sharpness = variance of Laplacian in the centre crop; higher is sharper. It depends on the scene, so compare between cameras and between still/motion, not against other cameras.
- Temporal noise = std of frame-to-frame difference / √2 on still frames (includes any flicker).

Motion blur (cam 0): sharpness relative to the 9 surrounding frames, by angular rate at capture (1.00 = as sharp as its neighbours):

| angular rate (°/s) | frames | relative sharpness |
|---|---|---|
| (0, 30] | 150 | 1.00 |
| (30, 60] | 220 | 1.00 |
| (60, 100] | 168 | 1.00 |
| (100, 150] | 175 | 1.00 |
| (150, 200] | 102 | 1.00 |
| (200, 1000] | 48 | 1.07 |

- Fastest frame: 270 °/s at t=43.3 s (frame 628), relative sharpness 1.57. (Frame image not included in this repo.)

## Camera–IMU time alignment

Optical-flow rate of each camera vs gyro rate, cross-correlated over ±150 ms:

| cam | best offset (ms) | correlation at best | correlation at 0 ms |
|---|---|---|---|
| 0 | +0 | 0.951 | 0.951 |
| 2 | +0 | 0.957 | 0.957 |

Frames arrive only every 66–100 ms here, so treat this as ±10 ms resolution. See `sync.png`.

Plots: `allan.png`, `imu_motion.png`, `sync.png`.
