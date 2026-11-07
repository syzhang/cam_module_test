# Camera module test

Install, stream-test, record and analyse a multi-sensor camera module (4 fisheye cameras, IMU, RGB, ToF) on Linux.
It measures delivery (frame and IMU loss, and latency, against the camera's own clock), image quality, IMU quality
and image–IMU time alignment, and writes one combined report.

The first round of tests ran in WSL2 on Windows, where USB passthrough lost ~60% of the data. Those
results are in [`docs/wsl_results/`](docs/wsl_results/TEST_SUMMARY.md). This repo repeats the same tests on a native Linux machine.

## Quick start (native Ubuntu)

The vendor SDK is **not** included in this repo; it is proprietary. Use the SDK package from the module vendor.
By default `sdk.conf` expects it unzipped into a `vendor_sdk` folder next to this repo:

```text
some_dir/
├── vendor_sdk/          # the unzipped vendor SDK package (any layout inside)
└── cam_module_test/     # this repo
```

```bash
git clone <this repo> cam_module_test && cd cam_module_test
unzip <vendor SDK package>.zip -d ../vendor_sdk    # or set SDK_DIR in sdk.conf
./setup.sh                    # apt deps, SDK .deb, udev rule, .venv, builds recorder + vendor demos
scripts/check_camera.sh       # USB 3 link + 4 s stream probe
scripts/run_full_test.sh      # everything (~25 min, the 10-min part is interactive)
                              # or add --short: check + 3-min guided test + analysis (~5 min)
                              # or add --quick: check + 5-min guided test with SLAM + analysis (~10 min)
```

`setup.sh` finds the SDK's `.deb` and udev rule anywhere inside that folder. `./setup.sh --sdk /path/to/sdk` overrides
the path for a single run. `sdk.conf` also records the SHA-256 of the SDK build used for these tests, and setup warns
if yours differs.

The combined report is written to `data/<stamp>_fulltest/REPORT.md`.

**Requirements**
- Ubuntu 20.04 x86_64. This is the SDK's target; 24.04 also worked.
- A **USB 3** port and cable. At USB 2 the fisheye cameras send nothing, with no error.
- About 25 GB free disk: 10 minutes of images at 30 fps is about 20 GB.
- A desktop session for the vendor demos and the optional `--show` preview.

## What the full test does

| step | what | time |
|---|---|---|
| 1. camera check | USB link speed (needs 5000 Mbps), 4 s probe of IMU + fisheye | 10 s |
| 2. stream test | IMU, fisheye, RGB, ToF each started alone through the SDK's Python wrapper: OK / crash / no data | 1 min |
| 3. vendor demos | the SDK's own demo programs (RGB only, fisheye + IMU, ToF only, C interface) under gdb, to tell SDK bugs from ours | 1 min |
| 4. comparison sessions | 30 s each: streams only, + saving images, + SDK SLAM | 2 min |
| 5. guided test | 10 min of timed cues: rests, slow/fast pitch/yaw/roll, translations, walking, mixed fast motion | 10 min |
| 6. analysis | delivery, image metrics (slow part), IMU and image–IMU analysis | 5–15 min |

Between steps the script re-checks the camera. If it has dropped off USB, the script asks you to re-plug it.
Options: `--quick`, `--short`, `--no-demos`, `--no-sessions`, `--show` (live preview during the guided test).

`--short` runs only steps 1, 5 and 6, with a 3-minute guided test that puts fast motion last, so a loose cable costs the
least. Without the stream test the report has no firmware version, and with 15–25 s rests its IMU noise figures are rougher.
`--quick` also runs only steps 1, 5 and 6: 5 minutes with SLAM on throughout, including a slide along the long edge of a
14-inch MacBook Pro (about 31.3 cm) and back, to check SLAM's distance. In every mode, the guided test stops and says so if the IMU data stops arriving for 6 s.

## Individual tools

| command | purpose |
|---|---|
| `scripts/check_camera.sh` | USB 3 link + stream probe |
| `scripts/test_streams.sh [out] [imu stereo rgb tof]` | per-stream smoke test → `streams.md` |
| `scripts/vendor_demos.sh [out]` | vendor demos under gdb → `vendor_demos.md` |
| `scripts/record.sh <name> <s> [--no-images] [--slam] [--show] [--save-every N]` | one recording |
| `scripts/record_sessions.sh [s]` | streams / +images / +SLAM comparison |
| `scripts/record_protocol.sh [name] [--quick \| --short \| --slam] [--show]` | guided 10-minute test, 5-minute test with SLAM, 3-minute test, or 75-second SLAM check |
| `scripts/analyze_session.sh <session>` | all analyses for one recording |
| `analysis/module_quality.py <still> <motion>` | quality report from a separate still + motion recording |
| `scripts/export_frame.sh <session> <frame> <out.png>` | all 4 cameras of one frame as a PNG |
| `scripts/sysinfo.sh` | machine / OS / SDK / camera table |

Settings come from environment variables, set in `scripts/common.sh`: `DATA_DIR` (default `./data`), `BUILD_DIR` (default `./build`) and `PYTHON` (default `.venv/bin/python`).

## Recording format (`recorder/cam_recorder.cpp`)

Every sample carries three clocks, which is what makes loss and latency measurable:

- `edge_us`: the camera's own clock, when the sample was captured.
- `host_s`: the SDK's capture time, mapped onto the host's steady clock.
- `arrival_s`: when the data actually reached the program, on the host's steady clock.

| file | columns |
|---|---|
| `imu.csv` | `edge_us, host_s, arrival_s, gx, gy, gz (rad/s), ax, ay, az (m/s²), temp_k` |
| `fisheye.csv` | `frame, device_id, edge_us, host_s, arrival_s, n_images, width, height, saved` |
| `pose.csv` (`--slam`) | `edge_us, host_s, arrival_s, x, y, z, qx, qy, qz, qw, confidence` |
| `fisheye/<frame>_<cam>.pgm` | raw 8-bit images, cams 0–3 |
| `phases.csv` (guided test) | cue schedule: `start_s, end_s, phase, instruction` |

## Reading the results

**[docs/READING_RESULTS.md](docs/READING_RESULTS.md)** is the full guide: a pass/fail checklist, what every section and
column of `REPORT.md` means, how loss and latency are measured, and where each output file is.

The most important checks, with suggested targets for a VIO camera (rules of thumb, not vendor specs) next to the
WSL2 results:

| check | suggested target | WSL2 (USB/IP) |
|---|---|---|
| USB link | 5000 Mbps | 5000 Mbps (480 once: no fisheye at all) |
| fisheye delivered | ≈ 30 fps, loss < 1% | 9–14 fps, 52–63% lost |
| IMU delivered | ≈ 500 Hz, loss < 1% | 145–310 Hz, 37–71% lost |
| fisheye latency (median) | < 50 ms | 230–300 ms |
| image–IMU offset | within ±5 ms, no drift | +1.4 ± 4.1 ms, no drift |
| gyro noise at rest | < 0.2 °/s per axis | 0.12–0.18 °/s; y-axis 0.43 °/s |
| motion blur at 150–300 °/s | relative sharpness ≥ 0.9 | 1.00 (none) |
| module drop-outs | none | 5 in one day |

If delivery is good natively, the WSL losses came from USB passthrough. If it is still bad, report the numbers to the vendor.

## Known issues (from the WSL round)

- The RGB stream crashes inside the SDK's video library; the vendor's own demos crash too.
- ToF is disabled in the module's configuration.
- The module hung or dropped off USB repeatedly, and needed a re-plug each time.
- The fisheye frame ID is always 0, and the IMU temperature is always 0 K.
- The SDK's stock Python wrapper overflows its frame buffers. `scripts/smoke_test.py` works around this.
- One SDK header doesn't compile on GCC 13 without `#include <cstdint>`; the recorder includes it first.

## WSL

The scripts also run in WSL2. Install [usbipd-win](https://github.com/dorssel/usbipd-win) on Windows, then bind the
camera once from an admin PowerShell: `usbipd list`, then `usbipd bind --busid <BUSID>`. The scripts attach it
automatically after that. `tools/windows/native_baseline.py` was an attempt to stream the raw UVC interfaces on Windows
without the SDK; it showed the module sends no frames without the SDK.

## Contents

- `sdk.conf`: where the vendor SDK lives, and the checksum of the build tested. The SDK itself is not in the repo.
- `setup.sh`: one-time install and build.
- `recorder/`: the C++ recorder (SDK callbacks → CSV + PGM).
- `scripts/`: setup checks, tests, recording, the runner.
- `analysis/`: Python analysis.
- `docs/READING_RESULTS.md`: how to read the reports.
- `docs/wsl_results/`: the WSL test summary, reports and plots, and the CSVs of the 7-minute guided run for re-analysis.
