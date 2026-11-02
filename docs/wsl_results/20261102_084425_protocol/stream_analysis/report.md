# Stream report: 20261102_084425_protocol

Recorder settings: duration_s=600.018, imu_samples=82335, fisheye_frames=5223, pose_samples=0, save_images=1, save_every=1, images_not_written=0, slam=0

| metric | imu | fisheye |
|---|---|---|
| samples | 82335 | 5216 |
| corrupt timestamps (dropped) | 0 | 7 |
| duration (s) | 424.9 | 424.6 |
| received rate (Hz) | 193.8 | 12.3 |
| nominal rate (Hz) | 503.8 | 30.0 |
| missing samples | 131736 | 7521 |
| loss % | 61.5 | 59.0 |
| device interval median / std (ms) | 3.97 / 4.68 | 66.67 / 18.02 |
| arrival interval median / std (ms) | 3.42 / 4.61 | 81.16 / 11.48 |
| arrival interval p99 / max (ms) | 23.1 / 58.4 | 108.8 / 235.4 |
| burst deliveries % | 0.0 | 0.0 |
| latency median (ms) | 1.8 | 277.0 |
| latency p95 / p99 / max (ms) | 8.1 / 12.1 / 39.1 | 312.4 / 328.1 / 364.0 |

- **imu** device-interval multiples of nominal (base device interval): 1x: 32077, 2x: 26088, 3x: 7847, 4x: 3708, 5x: 3172, 6x: 3283, 7x: 2173, 8x: 1267, 9x: 856, 10x: 582, 11x: 395, 12x: 269, 13x: 187, 14x: 139, 15x: 91, 16x: 59, 17x: 39, 18x: 32, 19x: 15, 20x: 17, 21x: 12, 22x: 7, 23x: 5, 24x: 1, 25x: 7, 27x: 3, 28x: 1, 29x: 1, 34x: 1
- **fisheye** device-interval multiples of nominal (configured): 1x: 64, 2x: 2830, 3x: 2278, 4x: 37, 5x: 6

Plots:
- imu.png
- imu_signals.png
- fisheye.png
