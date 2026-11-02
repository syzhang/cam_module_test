# Protocol test: 20261102_081710_protocol

Recorded 600 s of IMU (186621 samples) and 0 fisheye frames. Phases trimmed by 2 s at each edge.

## Delivery by phase (WSL USB/IP)

| phase | time (s) | median |gyro| (°/s) | IMU Hz | IMU loss % | fisheye fps | fisheye loss % | fisheye latency (ms) |
|---|---|---|---|---|---|---|---|---|
| still_start | 0–60 | 0 | 320 | 36 | nan | nan | nan |
| slow_pitch | 60–80 | 0 | 302 | 40 | nan | nan | nan |
| slow_yaw | 80–100 | 56 | 309 | 38 | nan | nan | nan |
| slow_roll | 100–120 | 50 | 324 | 35 | nan | nan | nan |
| still_1 | 120–140 | 1 | 328 | 34 | nan | nan | nan |
| fast_pitch | 140–160 | 121 | 317 | 37 | nan | nan | nan |
| fast_yaw | 160–180 | 199 | 340 | 32 | nan | nan | nan |
| fast_roll | 180–200 | 173 | 324 | 35 | nan | nan | nan |
| still_2 | 200–220 | 1 | 319 | 36 | nan | nan | nan |
| translate_fb | 220–250 | 10 | 325 | 35 | nan | nan | nan |
| translate_lr | 250–280 | 16 | 296 | 41 | nan | nan | nan |
| translate_ud | 280–300 | 24 | 333 | 33 | nan | nan | nan |
| still_3 | 300–320 | 1 | 316 | 37 | nan | nan | nan |
| walk | 320–480 | 67 | 297 | 41 | nan | nan | nan |
| still_4 | 480–500 | 0 | 311 | 38 | nan | nan | nan |
| mixed_fast | 500–540 | 92 | 310 | 38 | nan | nan | nan |
| still_end | 540–600 | 1 | 304 | 39 | nan | nan | nan |

- Average over still phases: IMU loss 37%, fisheye loss nan%, latency nan ms; over motion phases: IMU loss 37%, fisheye loss nan%, latency nan ms.

Rest periods detected from the data (|gyro| < 2°/s for ≥ 5 s, 1 s trimmed each side): rest_1 1–72 s, rest_2 128–145 s, rest_3 207–224 s, rest_4 308–324 s, rest_5 480–511 s, rest_6 564–599 s.

## IMU in the rest periods

| phase | at (s) | gyro bias x / y / z (°/s) | gyro noise x / y / z (°/s) | accel noise (mg) | |g| (m/s²) | gravity dir vs first rest (°) | 95th pct motion (°/s) |
|---|---|---|---|---|---|---|---|
| rest_1 | 1 | +0.028 / -0.168 / +0.191 | 0.147 / 0.373 / 0.105 | 1.61 | 9.7933 | 0.0 | 0.82 |
| rest_2 | 127 | +0.059 / +0.039 / +0.197 | 0.227 / 0.384 / 0.123 | 2.12 | 9.7881 | 6.3 | 0.91 |
| rest_3 | 207 | +0.133 / +0.201 / +0.234 | 0.154 / 0.393 / 0.110 | 1.64 | 9.7870 | 5.9 | 0.86 |
| rest_4 | 307 | +0.112 / +0.129 / +0.237 | 0.176 / 0.400 / 0.110 | 1.65 | 9.7836 | 14.6 | 0.87 |
| rest_5 | 479 | +0.147 / +0.181 / +0.281 | 0.205 / 0.429 / 0.121 | 1.73 | 9.7661 | 52.5 | 0.97 |
| rest_6 | 564 | +0.128 / +0.160 / +0.230 | 0.179 / 0.392 / 0.113 | 1.67 | 9.7720 | 38.2 | 0.88 |

- Gyro bias spread across the 6 rest periods (max − min): 0.119 / 0.368 / 0.090 °/s (x/y/z).
- A rest period whose 95th-percentile motion is above ~1°/s was probably not fully still (camera touched / table bumped); treat its bias as less reliable.

## Gyro integration over the whole run

Gravity direction propagated with the gyro from the start, compared with the accelerometer in each rest period (all transport gaps included):

| rest | at (s) | bias-corrected | bias-corrected, trapezoid across gaps | raw gyro |
|---|---|---|---|---|
| rest_1 | 1 | 0.1° | 0.1° | 9.1° |
| rest_2 | 128 | 2.4° | 1.8° | 32.7° |
| rest_3 | 207 | 31.2° | 31.3° | 59.0° |
| rest_4 | 308 | 36.4° | 36.0° | 80.5° |
| rest_5 | 480 | 55.6° | 59.7° | 116.2° |
| rest_6 | 564 | 70.0° | 74.4° | 129.1° |

Rest periods have no linear acceleration, so this mismatch is pure orientation error from gyro bias/scale and from rotation lost in dropped samples.

Effect of sample loss (received samples thinned further at random, trapezoid integration, mean mismatch over rests 2…6):

| effective IMU loss | mean mismatch |
|---|---|
| 38% | 40.6° |
| 50% | 50.4° |
| 63% | 58.9° |
| 75% | 68.5° |
| 84% | 74.9° |

- Linear fit: mismatch ≈ 13.1° + 73.4° × loss. **Extrapolated to 0% loss: ~13°**; at the observed 38% loss: 41°. So roughly 68% of the integration error comes from dropped samples, the rest from the gyro itself (bias change, scale/axis errors) or from the bias estimate.

## Motion phases

| phase | peak |gyro| (°/s) | dominant gyro axis (share of rotation) | peak |accel| (g) | fisheye tracks/frame | image motion (px/frame) | rel. sharpness |
|---|---|---|---|---|---|---|
| slow_pitch | 158 | x (64% / 17% / 19%) | 1.36 | nan | nan | nan |
| slow_yaw | 188 | y (18% / 63% / 20%) | 1.30 | nan | nan | nan |
| slow_roll | 403 | y (30% / 36% / 34%) | 1.32 | nan | nan | nan |
| fast_pitch | 567 | x (68% / 13% / 18%) | 1.84 | nan | nan | nan |
| fast_yaw | 727 | y (15% / 60% / 25%) | 1.95 | nan | nan | nan |
| fast_roll | 525 | y (36% / 42% / 23%) | 1.92 | nan | nan | nan |
| translate_fb | 125 | x (47% / 23% / 30%) | 1.41 | nan | nan | nan |
| translate_lr | 73 | y (22% / 47% / 31%) | 1.14 | nan | nan | nan |
| translate_ud | 52 | y (25% / 49% / 26%) | 1.16 | nan | nan | nan |
| walk | 359 | y (33% / 44% / 23%) | 1.77 | nan | nan | nan |
| mixed_fast | 389 | x (48% / 31% / 21%) | 3.41 | nan | nan | nan |

- Dominant axis in the slow/fast pitch, yaw and roll phases gives the IMU axis mapping (which body axis is which).
- Relative sharpness is vs the first rest period; it also changes with the scene, so read it together with the image-motion column.

Plots: `overview.png` (green = detected rest periods, dotted = cue times), `allan_rest.png`, `loss_vs_error.png`.
