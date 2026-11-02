# Protocol test: 20261102_084425_protocol

Recorded 425 s of IMU (82335 samples) and 5216 fisheye frames. Phases trimmed by 2 s at each edge.

**Recording ended early at 425 s** (device stopped or test aborted).

## Delivery by phase (WSL USB/IP)

| phase | time (s) | median |gyro| (°/s) | IMU Hz | IMU loss % | fisheye fps | fisheye loss % | fisheye latency (ms) |
|---|---|---|---|---|---|---|---|---|
| still_start | 0–60 | 0 | 177 | 65 | 11.6 | 61 | 288 |
| slow_pitch | 60–80 | 5 | 183 | 63 | 11.6 | 61 | 288 |
| slow_yaw | 80–100 | 72 | 191 | 62 | 11.7 | 61 | 282 |
| slow_roll | 100–120 | 93 | 190 | 62 | 12.0 | 60 | 281 |
| still_1 | 120–140 | 11 | 192 | 62 | 12.1 | 59 | 275 |
| fast_pitch | 140–160 | 1 | 191 | 62 | 12.0 | 60 | 281 |
| fast_yaw | 160–180 | 183 | 171 | 66 | 11.7 | 61 | 287 |
| fast_roll | 180–200 | 160 | 181 | 64 | 11.4 | 62 | 292 |
| still_2 | 200–220 | 1 | 187 | 63 | 11.9 | 60 | 284 |
| translate_fb | 220–250 | 21 | 173 | 65 | 11.5 | 62 | 290 |
| translate_lr | 250–280 | 32 | 223 | 55 | 14.6 | 51 | 229 |
| translate_ud | 280–300 | 32 | 232 | 54 | 14.6 | 51 | 232 |
| still_3 | 300–320 | 1 | 212 | 58 | 13.1 | 56 | 265 |
| walk | 320–480 | 74 | 202 | 60 | 12.4 | 59 | 272 |

- Average over still phases: IMU loss 62%, fisheye loss 59%, latency 278 ms; over motion phases: IMU loss 61%, fisheye loss 59%, latency 273 ms.

Rest periods detected from the data (|gyro| < 2°/s for ≥ 5 s, 1 s trimmed each side): rest_1 4–69 s, rest_2 135–152 s, rest_3 210–225 s, rest_4 306–335 s.

## IMU in the rest periods

| phase | at (s) | gyro bias x / y / z (°/s) | gyro noise x / y / z (°/s) | accel noise (mg) | |g| (m/s²) | gravity dir vs first rest (°) | 95th pct motion (°/s) |
|---|---|---|---|---|---|---|---|
| rest_1 | 3 | +0.019 / -0.166 / +0.212 | 0.176 / 0.430 / 0.120 | 1.67 | 9.7822 | 0.0 | 0.95 |
| rest_2 | 134 | +0.050 / -0.005 / +0.257 | 0.177 / 0.425 / 0.116 | 1.82 | 9.7828 | 21.4 | 0.94 |
| rest_3 | 210 | +0.087 / -0.002 / +0.241 | 0.168 / 0.449 / 0.124 | 1.64 | 9.7800 | 18.3 | 0.95 |
| rest_4 | 305 | +0.060 / -0.087 / +0.215 | 0.165 / 0.440 / 0.120 | 1.71 | 9.7829 | 48.9 | 0.96 |

- Gyro bias spread across the 4 rest periods (max − min): 0.068 / 0.164 / 0.045 °/s (x/y/z).
- A rest period whose 95th-percentile motion is above ~1°/s was probably not fully still (camera touched / table bumped); treat its bias as less reliable.

## Gyro integration over the whole run

Gravity direction propagated with the gyro from the start, compared with the accelerometer in each rest period (all transport gaps included):

| rest | at (s) | bias-corrected | bias-corrected, trapezoid across gaps | raw gyro |
|---|---|---|---|---|
| rest_1 | 4 | 1.3° | 1.2° | 9.6° |
| rest_2 | 135 | 5.4° | 1.4° | 37.9° |
| rest_3 | 210 | 40.7° | 40.3° | 67.0° |
| rest_4 | 306 | 45.3° | 46.1° | 88.9° |

Rest periods have no linear acceleration, so this mismatch is pure orientation error from gyro bias/scale and from rotation lost in dropped samples.

Effect of sample loss (received samples thinned further at random, trapezoid integration, mean mismatch over rests 2…4):

| effective IMU loss | mean mismatch |
|---|---|
| 61% | 29.3° |
| 69% | 34.7° |
| 77% | 41.2° |
| 84% | 48.1° |
| 90% | 49.8° |

- Linear fit: mismatch ≈ -16.2° + 74.4° × loss. At the observed 61% loss the mean mismatch is 29°; the line reaches ~0° at 0% loss, so essentially all of it comes from dropped samples; the gyro's own contribution is below what this test can resolve (a few degrees). Random thinning is not identical to real transport gaps (those come in bursts), so treat this as an estimate.

## Motion blocks

Each block is the motion between two detected rest periods (cue steps it covers in brackets).

| block | time (s) | median / peak |gyro| (°/s) | gyro axis share x / y / z | peak |accel| (g) | tracks/frame | image motion (px/frame) |
|---|---|---|---|---|---|---|
| [slow_pitch+slow_yaw+slow_roll] | 69–135 | 76 / 276 | 34% / 41% / 25% | 1.66 | 192 | 29.7 |
| [fast_pitch+fast_yaw+fast_roll] | 152–210 | 154 / 448 | 38% / 43% / 19% | 2.07 | 144 | 60.5 |
| [translate_fb+translate_lr+translate_ud] | 225–306 | 29 / 187 | 31% / 46% / 23% | 1.36 | 210 | 10.4 |
| [walk] | 335–425 | 80 / 244 | 32% / 44% / 24% | 2.45 | 176 | 32.8 |

- Purest single-axis rotation found in any 3 s window: x 82%, y 76%, z 49% of the rotation on that axis. An axis that never dominates was not rotated cleanly on its own.

## Motion blur (cam 0)

Sharpness relative to the 9 surrounding frames (cancels scene changes), by angular rate at capture:

| angular rate (°/s) | frames | relative sharpness |
|---|---|---|
| (0, 30] | 2526 | 1.00 |
| (30, 60] | 790 | 1.00 |
| (60, 100] | 812 | 1.00 |
| (100, 150] | 614 | 1.00 |
| (150, 200] | 261 | 1.00 |
| (200, 300] | 156 | 1.00 |
| (300, 1000] | 64 | 0.94 |

## Image–IMU time alignment

Gyro rate vs feature-tracked image motion, cross-correlated over ±150 ms (positive = gyro shifted later).

| window | cam 0 offset (corr) | cam 2 offset (corr) |
|---|---|---|
| whole run | +1 ms (0.98) | +0 ms (0.92) |
| [slow_pitch+slow_yaw+slow_roll] | +4 ms (0.97) | +6 ms (0.92) |
| [fast_pitch+fast_yaw+fast_roll] | +2 ms (0.98) | +1 ms (0.92) |
| [translate_fb+translate_lr+translate_ud] | -1 ms (0.95) | +4 ms (0.73) |
| [walk] | -2 ms (0.90) | -6 ms (0.69) |

- Sliding 30 s windows with correlation > 0.8 (43 windows): offset mean +1.4 ms, std 4.1 ms, range -11…+10 ms. No drift over time means image and IMU timestamps stay locked together.


Plots: `overview.png` (green = detected rest periods, dotted = cue times), `allan_rest.png`, `loss_vs_error.png`, `sync_over_time.png`.
