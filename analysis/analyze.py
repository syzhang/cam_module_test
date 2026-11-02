"""Analyse a recording made by cam_recorder: rates, drops, latency and jitter per stream.

Usage:
    python analyze.py <session_dir> [<session_dir> ...] [--fe-fps 30] [--out DIR]

For each session writes report.md and plots (PNG) into --out (default: <session_dir>/analysis).

Clocks in the CSVs:
    edge_us   camera clock: when the sample was captured, as stamped by the device
    host_s    SDK's estimate of the capture time on the host clock (mapped from edge_us)
    arrival_s when the callback actually ran on the host
So: edge-clock gaps = samples the camera produced but we never got (or never produced);
arrival - host_s = transport + SDK latency; arrival intervals = delivery jitter / burstiness.
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def base_period(d_ms):
    """Smallest device interval that is common (>=2% of samples).

    With losses the median is a multiple of the true period (e.g. IMU: median 4 ms but the
    sensor actually samples every 2 ms), so take the lowest well-populated interval instead.
    """
    counts = pd.Series(np.round(d_ms, 1)).value_counts()
    common = counts[counts >= 0.02 * len(d_ms)].index
    if not len(common):
        return float(np.median(d_ms))
    lo = float(min(common))
    near = d_ms[np.abs(d_ms - lo) < 0.25 * lo]
    return float(np.median(near))


def stream_stats(df, name, nominal_hz=None):
    # Drop samples with corrupted device timestamps (seen: one fisheye frame stamped 3.6e17 us):
    # device time minus arrival time should be near-constant; anything >1 s off is bogus.
    offset = df["edge_us"] / 1e6 - df["arrival_s"]
    good = (offset - offset.median()).abs() < 1.0
    corrupt = int((~good).sum())
    df = df[good].sort_values("edge_us").reset_index(drop=True)
    edge = df["edge_us"].to_numpy(dtype=np.int64)
    arrival = df["arrival_s"].to_numpy()
    host = df["host_s"].to_numpy()
    d_edge = np.diff(edge) / 1e3  # ms
    d_edge = d_edge[d_edge > 0]
    d_arr = np.diff(np.sort(arrival)) * 1e3
    span_s = (edge[-1] - edge[0]) / 1e6 if len(edge) > 1 else float("nan")

    period = 1000.0 / nominal_hz if nominal_hz else base_period(d_edge)
    steps = np.round(d_edge / period)
    missing = int(np.clip(steps - 1, 0, None).sum())
    expected = len(df) + missing
    latency = (arrival - host) * 1e3
    latency = latency[np.isfinite(latency)]

    s = {
        "stream": name,
        "samples": len(df),
        "corrupt": corrupt,
        "duration_s": span_s,
        "rate_hz": (len(df) - 1) / span_s if span_s else float("nan"),
        "nominal_hz": 1000.0 / period,
        "nominal_source": "configured" if nominal_hz else "base device interval",
        "missing": missing,
        "loss_pct": 100.0 * missing / expected if expected else float("nan"),
        "edge_dt_med_ms": float(np.median(d_edge)) if len(d_edge) else float("nan"),
        "edge_dt_std_ms": float(np.std(d_edge)) if len(d_edge) else float("nan"),
        "arr_dt_med_ms": float(np.median(d_arr)) if len(d_arr) else float("nan"),
        "arr_dt_std_ms": float(np.std(d_arr)) if len(d_arr) else float("nan"),
        "arr_dt_p99_ms": pct(d_arr, 99),
        "arr_dt_max_ms": float(d_arr.max()) if len(d_arr) else float("nan"),
        # Deliveries arriving < 1/4 period after the previous one = data delivered in bursts.
        "burst_pct": 100.0 * float(np.mean(d_arr < period / 4)) if len(d_arr) else float("nan"),
        "lat_med_ms": pct(latency, 50),
        "lat_p95_ms": pct(latency, 95),
        "lat_p99_ms": pct(latency, 99),
        "lat_max_ms": float(latency.max()) if len(latency) else float("nan"),
        "step_hist": pd.Series(steps.astype(int)).value_counts().sort_index().to_dict(),
    }
    return s, d_edge, d_arr, latency, period, df


def plot_stream(name, d_edge, d_arr, latency, period, df, out):
    fig, ax = plt.subplots(1, 3, figsize=(16, 4))
    ax[0].hist(d_edge / period, bins=np.arange(0.25, max(6, np.nanmax(d_edge / period) + 1), 0.05), color="tab:blue")
    ax[0].set_xlabel("device-clock interval / nominal period")
    ax[0].set_ylabel("count")
    ax[0].set_title("%s: capture gaps (1 = no drop, 2 = one missing...)" % name)
    ax[1].hist(np.clip(d_arr, 0, period * 6), bins=120, color="tab:orange")
    ax[1].axvline(period, color="k", ls="--", lw=1, label="nominal %.1f ms" % period)
    ax[1].set_xlabel("host arrival interval (ms)")
    ax[1].set_title("%s: delivery jitter" % name)
    ax[1].legend()
    t = df["arrival_s"].to_numpy() - df["arrival_s"].min()
    lat = (df["arrival_s"] - df["host_s"]).to_numpy() * 1e3
    ax[2].plot(t, lat, ".", ms=2, color="tab:red")
    ax[2].set_xlabel("time (s)")
    ax[2].set_ylabel("arrival - capture (ms)")
    ax[2].set_title("%s: latency over time" % name)
    fig.tight_layout()
    path = os.path.join(out, "%s.png" % name)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_imu(df, out):
    t = (df["edge_us"] - df["edge_us"].min()) / 1e6
    fig, ax = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
    for c in ("ax", "ay", "az"):
        ax[0].plot(t, df[c], lw=0.7, label=c)
    ax[0].set_ylabel("accel (m/s²)")
    ax[0].legend(loc="upper right")
    for c in ("gx", "gy", "gz"):
        ax[1].plot(t, df[c], lw=0.7, label=c)
    ax[1].set_ylabel("gyro (rad/s)")
    ax[1].set_xlabel("device time (s)")
    ax[1].legend(loc="upper right")
    fig.tight_layout()
    path = os.path.join(out, "imu_signals.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def plot_pose(df, out):
    fig = plt.figure(figsize=(12, 5))
    a = fig.add_subplot(1, 2, 1)
    t = (df["edge_us"] - df["edge_us"].min()) / 1e6
    for c in ("x", "y", "z"):
        a.plot(t, df[c], lw=0.8, label=c)
    a.set_xlabel("device time (s)")
    a.set_ylabel("position (m)")
    a.legend()
    a.set_title("SLAM position")
    b = fig.add_subplot(1, 2, 2)
    b.plot(df["x"], df["z"], lw=0.8)
    b.set_aspect("equal", adjustable="datalim")
    b.set_xlabel("x (m)")
    b.set_ylabel("z (m)")
    b.set_title("trajectory (top view)")
    fig.tight_layout()
    path = os.path.join(out, "pose.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


ROWS = [
    ("samples", "samples", "%d"),
    ("corrupt timestamps (dropped)", "corrupt", "%d"),
    ("duration (s)", "duration_s", "%.1f"),
    ("received rate (Hz)", "rate_hz", "%.1f"),
    ("nominal rate (Hz)", "nominal_hz", "%.1f"),
    ("missing samples", "missing", "%d"),
    ("loss %", "loss_pct", "%.1f"),
    ("device interval median / std (ms)", ("edge_dt_med_ms", "edge_dt_std_ms"), "%.2f / %.2f"),
    ("arrival interval median / std (ms)", ("arr_dt_med_ms", "arr_dt_std_ms"), "%.2f / %.2f"),
    ("arrival interval p99 / max (ms)", ("arr_dt_p99_ms", "arr_dt_max_ms"), "%.1f / %.1f"),
    ("burst deliveries %", "burst_pct", "%.1f"),
    ("latency median (ms)", "lat_med_ms", "%.1f"),
    ("latency p95 / p99 / max (ms)", ("lat_p95_ms", "lat_p99_ms", "lat_max_ms"), "%.1f / %.1f / %.1f"),
]


def fmt(s, key, f):
    if isinstance(key, tuple):
        return f % tuple(s[k] for k in key)
    return f % s[key]


def analyze(session, fe_fps, out):
    out = out or os.path.join(session, "analysis")
    os.makedirs(out, exist_ok=True)
    stats, plots = [], []
    imu = pd.read_csv(os.path.join(session, "imu.csv"))
    s, *rest = stream_stats(imu, "imu")
    stats.append(s)
    plots.append(plot_stream("imu", *rest, out))
    plots.append(plot_imu(imu, out))
    fe = pd.read_csv(os.path.join(session, "fisheye.csv"))
    s, *rest = stream_stats(fe, "fisheye", fe_fps)
    stats.append(s)
    plots.append(plot_stream("fisheye", *rest, out))
    pose_path = os.path.join(session, "pose.csv")
    if os.path.exists(pose_path) and os.path.getsize(pose_path) > 100:
        pose = pd.read_csv(pose_path)
        s, *rest = stream_stats(pose, "pose")
        stats.append(s)
        plots.append(plot_stream("pose", *rest, out))
        plots.append(plot_pose(pose, out))

    meta = {}
    mp = os.path.join(session, "meta.txt")
    if os.path.exists(mp):
        meta = dict(l.strip().split("=", 1) for l in open(mp) if "=" in l)

    lines = ["# Stream report: %s" % os.path.basename(os.path.normpath(session)), ""]
    if meta:
        lines += ["Recorder settings: " + ", ".join("%s=%s" % kv for kv in meta.items()), ""]
    lines.append("| metric | " + " | ".join(s["stream"] for s in stats) + " |")
    lines.append("|---|" + "---|" * len(stats))
    for label, key, f in ROWS:
        lines.append("| %s | %s |" % (label, " | ".join(fmt(s, key, f) for s in stats)))
    lines.append("")
    for s in stats:
        hist = ", ".join("%dx: %d" % kv for kv in s["step_hist"].items())
        lines.append("- **%s** device-interval multiples of nominal (%s): %s" % (s["stream"], s["nominal_source"], hist))
    lines += ["", "Plots:"] + ["- %s" % os.path.basename(p) for p in plots]
    report = "\n".join(lines) + "\n"
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print("written to", out)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--fe-fps", type=float, default=30.0, help="configured fisheye rate (device config says 30)")
    ap.add_argument("--out", help="output dir (only with a single session)")
    a = ap.parse_args()
    for sess in a.sessions:
        analyze(sess, a.fe_fps, a.out if len(a.sessions) == 1 else None)
