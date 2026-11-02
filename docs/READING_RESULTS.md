# Reading the results

`scripts/run_full_test.sh` writes `data/<stamp>_fulltest/REPORT.md`. This guide explains each section of that
report, what to look at first, and when a number is a problem.

## 1. Start here: the checklist

Fill this in from `REPORT.md`. The thresholds are **suggested rules of thumb** for a camera used for visual-inertial
tracking (VIO/SLAM), not vendor specifications. The last column is what WSL2 measured, for comparison.

| check | where in REPORT.md | good | look into it | WSL2 result |
|---|---|---|---|---|
| USB link | Test machine → camera | 5000 Mbps | 480 Mbps (fisheye won't stream at all) | 5000 (480 once) |
| streams start | §1–2 Streams | IMU + stereo `OK` | `CRASH`, `HANG`, `no data` | IMU, stereo OK; RGB crash; ToF no data |
| fisheye delivery | §5 delivery: fisheye `loss %` | < 1% (≈ 30 fps) | > 5% | 52–63% (9–14 fps) |
| IMU delivery | §5 delivery: imu `loss %` | < 1% (≈ 500 Hz) | > 5% | 37–71% (145–310 Hz) |
| fisheye latency | §5: `latency median` | < 50 ms | > 100 ms | 230–300 ms |
| delivery jitter | §5: `arrival interval p99` | < 2 × period (fisheye < 67 ms, IMU < 4 ms) | much larger | 109 ms / 23 ms |
| corrupted timestamps | §5: `corrupt timestamps (dropped)` | 0 | any | 1–7 per run |
| camera drop-outs | console: "Camera not ready… re-plug" prompts; "camera is no longer connected" | none | any | 5 in one day |
| image–IMU offset | §6 Image–IMU time alignment | mean within ±5 ms, std < 5 ms, corr > 0.9, no trend | mean beyond ±10 ms, or a trend over time | +1.4 ± 4.1 ms, corr 0.98 |
| gyro noise | §6 IMU in the rest periods: gyro noise | < 0.2 °/s per axis | > 0.3 °/s | 0.12–0.18; **y 0.43** |
| gyro bias stability | §6: bias spread across rests | < 0.2 °/s | > 0.5 °/s | 0.05–0.16 °/s |
| accelerometer | §6: accel noise, \|g\| | < 3 mg; \|g\| within ±0.5% of 9.80 | > 5 mg; > 1% off | 1.6–1.8 mg; 9.78 (−0.3%) |
| gyro integration | §6 Gyro integration: last rest, bias-corrected | < 10° | > 20° | 45–70° (almost all from lost samples) |
| motion blur | §6 Motion blur: relative sharpness at 150–300 °/s | ≥ 0.9 | < 0.8 | 1.00 |
| trackable images | §6 Motion blocks: tracks/frame | > 100 | < 50 | 140–210 |
| image noise | `module_quality.py` / `image_metrics.csv`: tnoise | < 3 DN | > 5 DN | 1.6–2.0 DN |
| RGB, ToF | §1–2, §3 | stream OK | crash / no data | crash in SDK / disabled in config |

If the delivery rows are good on native Linux, WSL's USB passthrough caused the losses and latency. If they are still
bad, the module, its firmware or the SDK is the problem: report it with the numbers.

## 2. How loss and latency are measured

Every IMU sample and fisheye frame is logged with three timestamps:

| column | clock | meaning |
|---|---|---|
| `edge_us` | the camera's own clock (µs) | when the sample was **captured** |
| `host_s` | host steady clock (s) | the SDK's estimate of the capture time on the host clock (mapped from `edge_us`) |
| `arrival_s` | host steady clock (s) | when the sample **reached the program** |

- **Loss** is counted on the camera clock. The fisheye captures on a 30 fps grid (33.3 ms) and the IMU on a 2 ms grid
  (~500 Hz). A gap of 2 periods in `edge_us` means one sample was captured but never arrived, 3 periods means two, and so on.
  This counts real losses. It does not rely on frame IDs, which this firmware always sets to 0.
- **Latency** = `arrival_s − host_s`: transport plus SDK processing. The IMU's latency of 1–3 ms shows the SDK's clock
  mapping is consistent, so a large fisheye latency is real delay, not a clock offset.
- **Corrupted timestamps:** samples whose `edge_us` is off by more than 1 s from the others are dropped and counted.
  One fisheye frame stamped 3.6×10¹⁷ µs is an example.

## 3. REPORT.md, section by section

### Test machine
The machine, OS, kernel, environment (native or WSL), camera link speed, firmware, SDK version and the usbfs memory
limit. Check that the link is **5000 Mbps** and the environment says **native Linux**. If delivery is poor on native
Linux, the vendor's USB-bandwidth script raises the usbfs limit from its default of 16 MB. It is normally needed only
for multiple devices.

### §1–2. Streams
Each stream is started alone for 8 s through the SDK's Python wrapper.

| result | meaning |
|---|---|
| `OK` + rate | samples arrived; the rate is unique samples per second |
| `no data` | started without error, but nothing arrived. Expected for `tof`, which is disabled in the module's config |
| `CRASH (segfault)` | the process died. In WSL, `rgb` crashed inside the SDK's video library |
| `HANG (timeout)` | no exit within 60 s |
| "camera disconnected after X" | the module dropped off USB after that stream, so note which stream triggers it |

`stereo` is the fisheye stream; the wrapper exposes 2 of the 4 cameras. These rates come from polling the wrapper,
so they are only a rough check. The recorder's rates in §4–5 are the accurate ones.

### §3. Vendor demos
The SDK's own demo programs (a C++ stream demo and a C-interface demo), run under gdb. A `CRASH` here with a backtrace means the bug is in the
SDK, not in this repo's code. Include the backtrace when reporting it. "needs a desktop session" means the stream demo
couldn't open its windows; run it from a graphical login.

### §4. Sessions (30 s each)
Three short recordings. Each has the same delivery table as §5 (explained there).
- **streams** vs **images**: the same streams, but **images** also writes every frame to disk. If loss rises
  with images, the disk or CPU can't keep up; the recorder's `images not written` count shows the same thing.
- **slam**: the SDK's SLAM running on the host. "SLAM pose samples" should be in the hundreds per second. 0 means SLAM
  didn't start; in WSL it worked once and then stopped producing poses.

### §5. Guided test: delivery
The stream table for the whole 10-minute recording:

| row | read it as |
|---|---|
| `samples`, `duration (s)` | how much arrived, over how long (camera clock). A duration well under 600 s means the stream stopped early (the module dropped out) |
| `received rate` / `nominal rate` | delivered vs captured rate. The nominal rate is 30 fps for the fisheye (configured) and the base 2 ms interval for the IMU (detected) |
| `missing samples`, `loss %` | captured but never delivered (§2) |
| `device interval median / std` | spacing on the camera clock. With no loss, the median equals the period (33.3 ms / 2 ms) |
| `arrival interval median / std, p99 / max` | spacing as delivered: jitter, and the longest stall |
| `burst deliveries %` | arrivals much closer together than the period, meaning data held back and then released in bursts |
| `latency median, p95 / p99 / max` | `arrival − capture` (§2) |
| `device-interval multiples` | histogram of gaps in periods: `1x` = consecutive, `2x` = one missing, … With no loss, nearly everything is `1x` |

Plots in `protocol/analysis/`: `fisheye.png` and `imu.png` show the capture-gap histogram, the arrival-jitter
histogram and latency over time. `imu_signals.png` shows the raw accelerometer and gyro.

### §6. Guided test: IMU, images, image–IMU alignment

**Delivery by phase.** The same loss and latency numbers, split by the cue steps. Use it to check whether loss gets worse
during motion or while walking. The cue times are approximate, because people start each step a few seconds late.

**IMU in the rest periods.** Rests are found **from the data** (gyro below 2 °/s for at least 5 s), not from the cues.

| column | read it as |
|---|---|
| gyro bias x / y / z | the gyro's reading at rest (should be 0). Under ~1 °/s is normal for MEMS; SLAM estimates it continuously |
| gyro noise x / y / z | standard deviation at rest, per sample. One axis much noisier than the others is worth asking about |
| accel noise | standard deviation at rest, in mg (1 mg = 0.0098 m/s²) |
| \|g\| | accelerometer magnitude at rest, which should be local gravity (~9.78–9.83 m/s²) |
| gravity dir vs first rest | how differently the camera was put down. Not a quality measure |
| 95th pct motion | how still the rest really was. Above ~1 °/s means it was touched or bumped, so trust that rest's bias less |

"Gyro bias spread" is the largest change in bias across all rests: how stable the bias is over the 10 minutes.
`allan_rest.png` shows Allan deviation (below).

**Gyro integration over the whole run.** The gyro is integrated from the start to predict which way gravity points, and
that prediction is compared with the accelerometer in each rest. It answers one question: can the gyro track
orientation through the whole test?
- **bias-corrected** uses the first rest's bias; **trapezoid** fills each gap with the average of the samples at both ends;
  **raw** applies no bias correction. That shows what bias alone costs: about 20–40° per minute.
- The error grows with **lost samples**: rotation during a gap is never measured. So the report then **thins the samples
  further at random** and fits error against loss (`loss_vs_error.png`). Read the fitted value at 0% loss as the gyro's
  own error, and the rest as the cost of lost data. Random thinning isn't identical to real burst gaps, so treat it as an
  estimate. With a lossless link, this table directly shows the gyro's own drift.

**Motion blocks.** The motion between two rests, labelled with the cue steps it covers.
- **gyro axis share x / y / z** and the "purest single-axis rotation" line give the IMU axis mapping. In WSL,
  pitch (nod) was x and yaw (turn) was y.
- **tracks/frame**: corner features tracked between consecutive frames. Above ~100 means the images are rich enough for VIO.
- **image motion (px/frame)**: median feature displacement. It grows with speed and with gaps between delivered frames.

**Motion blur (cam 0).** Each frame's sharpness (variance of the Laplacian) is divided by the median of its 9 neighbours.
That cancels scene changes, because neighbouring frames see nearly the same scene, so 1.00 means "as sharp as the frames
around it". Binned by rotation rate: if it stays near 1.00 at high rates, there is no motion blur (global shutter, short
exposure).

**Image–IMU time alignment.** Gyro rate is compared with feature-tracked image motion, and the gyro is shifted by
−150 to +150 ms to find the best match.
- **offset**: the shift with the best correlation. 0 ms means image and IMU timestamps agree.
- **corr**: how well they match, from 0 to 1. Trust offsets with corr above ~0.8.
- **sliding 30 s windows** (`sync_over_time.png`): the offset across the run. A flat line means no drift. A slope would
  mean the camera and IMU clocks run at different rates.
- Resolution is limited by the delivered frame rate. At ~12 fps in WSL that was about ±10 ms; at 30 fps it is finer.
- Cam 2 (the second, upward/sideways pair) usually correlates a little lower, because it sees less texture.

**Overview plot** (`protocol/protocol_analysis/overview.png`): |gyro|, |accel|, fisheye latency and the gravity mismatch over
the run. Green bands are the detected rests and dotted lines the cue times. A latency trace that stops early shows when
the module dropped out.

## 4. Concepts used

- **Allan deviation** (`allan_rest.png`): noise averaged over windows of length τ. It falls while averaging helps
  (white noise), bottoms out, then rises as slow bias drift takes over. The minimum is the **bias instability**. With
  60 s rests this is only a rough lower bound; a proper measurement needs about an hour on a still surface.
- **Noise density**: per-sample noise ÷ √(bandwidth). It assumes the noise bandwidth is half the 500 Hz output rate, so
  it's an estimate, useful for comparing with IMU datasheets.
- **Global shutter**: all pixels are exposed at the same instant, so fast rotation doesn't skew the image.
- **DN** (digital number): a pixel value on the 0–255 scale.

## 5. Where everything is

| path (inside `data/<stamp>_fulltest/`) | contents |
|---|---|
| `REPORT.md` | the combined report |
| `streams/` | `streams.md`, per-stream logs (`smoke_*.log`), sample images |
| `vendor_demos/` | `vendor_demos.md`, full gdb logs |
| `session_{streams,images,slam}/` | 30 s recordings + `analysis/report.md` |
| `protocol/` | the guided test: `imu.csv`, `fisheye.csv`, `phases.csv`, `fisheye/*.pgm`, `recorder.log` |
| `protocol/analysis/` | delivery report + plots |
| `protocol/image_metrics.csv`, `protocol/contact_sheet.png` | per-frame image metrics; all 4 cameras at 6 moments |
| `protocol/protocol_analysis/` | `protocol_report.md`, `overview.png`, `allan_rest.png`, `loss_vs_error.png`, `sync_over_time.png` |

To look at a particular frame: `scripts/export_frame.sh data/<stamp>_fulltest/protocol <frame> out.png`.
To re-run the analysis on any recording: `scripts/analyze_session.sh <session_dir>`.

## 6. Limits

- One 10-minute run is a snapshot. Run it twice to see how much the numbers vary.
- Image metrics depend on the scene (lighting, texture). Compare cameras and runs in the same place.
- The rest bias and noise need truly still rests: hands off, no bumping the table.
- The reports include the module's serial number and machine details. `data/` is ignored by git, so keep them out of a public repo.
