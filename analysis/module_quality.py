"""Module quality assessment from a still and a motion recording.

Usage: python module_quality.py <still_session> <motion_session> [--out DIR]   (default: <motion_session>/quality_report)
Needs image_metrics.csv in each session dir (from image_metrics.py) for the camera sections.

Everything here uses the camera's own timestamps (edge_us), so it measures the sensors, not
WSL delivery. Dropped samples reduce how much data there is, but not what each sample says.
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

G = 9.80665
IMU_ODR = 500.0  # base device interval is ~2 ms (see analyze.py)
ACC, GYR = ["ax", "ay", "az"], ["gx", "gy", "gz"]


def load_imu(s):
    d = pd.read_csv(os.path.join(s, "imu.csv")).sort_values("edge_us").drop_duplicates("edge_us")
    d["t"] = (d["edge_us"] - d["edge_us"].iloc[0]) / 1e6
    return d.reset_index(drop=True)


def load_img(s):
    p = os.path.join(s, "image_metrics.csv")
    if not os.path.exists(p):
        return None
    m = pd.read_csv(p)
    m["t"] = (m["edge_us"] - m["edge_us"].min()) / 1e6
    return m


def allan_dev(t, x, taus):
    """Overlapping Allan deviation from irregular samples, after averaging into 10 ms bins."""
    bin_s = 0.01
    idx = np.floor(t / bin_s).astype(int)
    s = pd.Series(x).groupby(idx).mean()
    s = s.reindex(range(idx.min(), idx.max() + 1)).interpolate(limit_direction="both").to_numpy()
    out = []
    for tau in taus:
        m = int(round(tau / bin_s))
        if m < 1 or 2 * m >= len(s):
            out.append(np.nan)
            continue
        c = np.cumsum(np.insert(s, 0, 0.0))
        avg = (c[m:] - c[:-m]) / m
        diff = avg[m:] - avg[:-m]
        out.append(np.sqrt(0.5 * np.mean(diff ** 2)))
    return np.array(out)


def still_segments(d, thresh_dps=3.0, min_s=1.0):
    """Time ranges where |gyro| stays below a threshold (camera at rest)."""
    rate = np.degrees(np.linalg.norm(d[GYR].to_numpy(), axis=1))
    smooth = pd.Series(rate).rolling(25, center=True, min_periods=1).median().to_numpy()
    still = smooth < thresh_dps
    segs, start = [], None
    for i, s in enumerate(still):
        if s and start is None:
            start = i
        if (not s or i == len(still) - 1) and start is not None:
            end = i
            if d["t"].iloc[end] - d["t"].iloc[start] >= min_s:
                segs.append((d["t"].iloc[start], d["t"].iloc[end]))
            start = None
    return segs


def imu_static(d, label):
    a, g = d[ACC].to_numpy(), np.degrees(d[GYR].to_numpy())
    amag = np.linalg.norm(a, axis=1)
    return {
        "label": label, "duration_s": d["t"].iloc[-1] - d["t"].iloc[0], "samples": len(d),
        "acc_mean": a.mean(0), "acc_std": a.std(0), "g_mag": amag.mean(), "g_mag_std": amag.std(),
        "gyro_bias_dps": g.mean(0), "gyro_std_dps": g.std(0),
    }


def clock_drift_ppm(d):
    """Device clock vs host arrival: slope of the lower envelope (minimum latency per second)."""
    edge = d["edge_us"].to_numpy() / 1e6
    lag = d["arrival_s"].to_numpy() - edge
    sec = np.floor(edge - edge[0]).astype(int)
    df = pd.DataFrame({"sec": sec, "edge": edge, "lag": lag})
    env = df.loc[df.groupby("sec")["lag"].idxmin()]
    slope = np.polyfit(env["edge"], env["lag"], 1)[0]
    return slope * 1e6


def sync_offset(d, m, cam=0, max_ms=150):
    """Camera-IMU time offset: shift the gyro rate until it best matches optical-flow rate."""
    f = m[(m["cam"] == cam) & m["flow_px"].notna() & (m["dt_s"] > 0) & (m["tracks"].fillna(0) >= 30)].copy()
    f["flow_rate"] = f["flow_px"] / f["dt_s"]
    t_img = (f["edge_us"].to_numpy() - d["edge_us"].iloc[0]) / 1e6 - f["dt_s"].to_numpy() / 2  # mid-interval
    flow = f["flow_rate"].to_numpy()
    rate = np.degrees(np.linalg.norm(d[GYR].to_numpy(), axis=1))
    rate = pd.Series(rate).rolling(15, center=True, min_periods=1).mean().to_numpy()
    offsets = np.arange(-max_ms, max_ms + 1, 1) / 1e3
    corr = []
    for o in offsets:
        g = np.interp(t_img + o, d["t"].to_numpy(), rate)
        corr.append(np.corrcoef(g, flow)[0, 1])
    corr = np.array(corr)
    best = offsets[np.nanargmax(corr)]
    return best * 1e3, offsets * 1e3, corr, t_img, flow, rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("still")
    ap.add_argument("motion")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(a.motion, "quality_report")
    os.makedirs(out, exist_ok=True)

    still, motion = load_imu(a.still), load_imu(a.motion)
    img_still, img_motion = load_img(a.still), load_img(a.motion)
    L = ["# Module quality assessment", "",
         "Still session: `%s`  \nMotion session: `%s`" % (os.path.basename(a.still), os.path.basename(a.motion)), ""]

    # --- IMU at rest ----------------------------------------------------------------------
    st = imu_static(still, "still session")
    segs = still_segments(motion)
    L += ["## IMU at rest", "",
          "| | x | y | z |", "|---|---|---|---|",
          "| accel mean (m/s²) | %+.3f | %+.3f | %+.3f |" % tuple(st["acc_mean"]),
          "| accel noise std (m/s²) | %.4f | %.4f | %.4f |" % tuple(st["acc_std"]),
          "| accel noise (mg) | %.2f | %.2f | %.2f |" % tuple(st["acc_std"] / G * 1e3),
          "| gyro bias (°/s) | %+.3f | %+.3f | %+.3f |" % tuple(st["gyro_bias_dps"]),
          "| gyro noise std (°/s) | %.3f | %.3f | %.3f |" % tuple(st["gyro_std_dps"]),
          "| gyro noise density (°/s/√Hz, assuming %d Hz ODR) | %.4f | %.4f | %.4f |"
          % ((IMU_ODR,) + tuple(st["gyro_std_dps"] / np.sqrt(IMU_ODR / 2))),
          "| accel noise density (µg/√Hz) | %.0f | %.0f | %.0f |"
          % tuple(st["acc_std"] / G * 1e6 / np.sqrt(IMU_ODR / 2)),
          "",
          "- Gravity magnitude: **%.4f m/s²** (std %.4f), vs standard 9.80665: %+.2f%%."
          % (st["g_mag"], st["g_mag_std"], 100 * (st["g_mag"] / G - 1)),
          "- Tilt from gravity direction: %.1f° off the -y axis."
          % np.degrees(np.arccos(-st["acc_mean"][1] / np.linalg.norm(st["acc_mean"]))),
          "- Uncorrected gyro bias would drift heading by %.0f°/%.0f°/%.0f° per minute (x/y/z)."
          % tuple(np.abs(st["gyro_bias_dps"]) * 60), ""]

    # Bias repeatability: still segments in the motion session vs the still session.
    if segs:
        L += ["Bias repeatability (rest periods found in the motion session, |gyro| < 3°/s for ≥1 s):", "",
              "| segment | duration (s) | gyro bias x/y/z (°/s) | |g| (m/s²) |", "|---|---|---|---|",
              "| still session | %.0f | %+.3f / %+.3f / %+.3f | %.4f |"
              % ((st["duration_s"],) + tuple(st["gyro_bias_dps"]) + (st["g_mag"],))]
        for t0, t1 in segs:
            seg = motion[(motion["t"] >= t0) & (motion["t"] <= t1)]
            s = imu_static(seg, "")
            L.append("| motion %.1f–%.1f s | %.1f | %+.3f / %+.3f / %+.3f | %.4f |"
                     % ((t0, t1, t1 - t0) + tuple(s["gyro_bias_dps"]) + (s["g_mag"],)))
        L.append("")

    taus = np.logspace(-2, np.log10(still["t"].iloc[-1] / 4), 25)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
    bias_inst = []
    for c in GYR:
        ad = allan_dev(still["t"].to_numpy(), np.degrees(still[c].to_numpy()), taus)
        ax[0].loglog(taus, ad * 3600, label=c)
        bias_inst.append(np.nanmin(ad) * 3600)
    ax[0].set_xlabel("τ (s)")
    ax[0].set_ylabel("Allan deviation (°/h)")
    ax[0].set_title("Gyro Allan deviation (still, %.0f s)" % still["t"].iloc[-1])
    ax[0].grid(True, which="both", alpha=0.3)
    ax[0].legend()
    for c in ACC:
        ad = allan_dev(still["t"].to_numpy(), still[c].to_numpy(), taus)
        ax[1].loglog(taus, ad / G * 1e6, label=c)
    ax[1].set_xlabel("τ (s)")
    ax[1].set_ylabel("Allan deviation (µg)")
    ax[1].set_title("Accel Allan deviation")
    ax[1].grid(True, which="both", alpha=0.3)
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out, "allan.png"), dpi=110)
    plt.close(fig)
    L += ["- Gyro bias instability (Allan minimum, only %.0f s of data so a rough lower bound): "
          "%.1f / %.1f / %.1f °/h (x/y/z). See `allan.png`." % ((still["t"].iloc[-1],) + tuple(bias_inst)), ""]

    # --- IMU in motion --------------------------------------------------------------------
    g = np.degrees(motion[GYR].to_numpy())
    acc = motion[ACC].to_numpy()
    t_m = motion["t"].to_numpy()
    # Gravity consistency: propagate the gravity direction with the gyro (dg/dt = -w x g, body frame)
    # and compare it with the accelerometer whenever the camera isn't accelerating (|a| ~ g).
    # Any growing disagreement comes from gyro bias/scale error AND from samples lost in transport.
    quasi = np.abs(np.linalg.norm(acc, axis=1) - st["g_mag"]) < 0.3
    tilt = {}
    for label, bias in (("raw", np.zeros(3)), ("bias-corrected (still-session bias)", np.radians(st["gyro_bias_dps"]))):
        w = motion[GYR].to_numpy() - bias
        start = np.where(quasi)[0][:50]
        gb = acc[start].mean(0)
        gb /= np.linalg.norm(gb)
        err = np.full(len(t_m), np.nan)
        for i in range(1, len(t_m)):
            dt = t_m[i] - t_m[i - 1]
            gb = gb - np.cross(w[i - 1], gb) * dt
            gb /= np.linalg.norm(gb)
            if quasi[i]:
                a_n = acc[i] / np.linalg.norm(acc[i])
                err[i] = np.degrees(np.arccos(np.clip(np.dot(gb, a_n), -1, 1)))
        tilt[label] = err
    gaps = np.diff(t_m)
    lost_rot = np.degrees(np.sum(np.linalg.norm(motion[GYR].to_numpy()[:-1], axis=1) * np.where(gaps > 0.003, gaps - 0.002, 0)))
    L += ["## IMU in motion", "",
          "- Peak angular rate: %.0f / %.0f / %.0f °/s (x/y/z); peak |accel| %.1f m/s² (%.1f g)."
          % (tuple(np.abs(g).max(0)) + (np.linalg.norm(acc, axis=1).max(), np.linalg.norm(acc, axis=1).max() / G)),
          "- No values sit at a constant rail, so no sign of saturation at these motion levels.",
          "- The camera was moving for the whole recording (|gyro| never below ~20°/s), so there is no rest"
          " period here; the bias from the still session is used instead.",
          "- Rotation that happened inside transport gaps (estimated): %.0f° in total, i.e. the gyro has to"
          " be integrated across %.0f%% of the elapsed time without samples." % (
              lost_rot, 100 * np.sum(np.where(gaps > 0.003, gaps - 0.002, 0)) / (t_m[-1] - t_m[0])),
          "",
          "Gravity-consistency check (angle between gyro-propagated gravity and the accelerometer, at moments"
          " with |a| within 0.3 m/s² of g):", "",
          "| gyro | after 10 s | after 30 s | after 60 s | median |", "|---|---|---|---|---|"]
    for label, err in tilt.items():
        def at(sec):
            m = (t_m > sec - 2) & (t_m <= sec) & ~np.isnan(err)
            return np.nanmedian(err[m]) if m.any() else np.nan
        L.append("| %s | %.1f° | %.1f° | %.1f° | %.1f° |" % (label, at(10), at(30), t_m[-1] and at(t_m[-1]), np.nanmedian(err)))
    L += ["", "A few degrees of disagreement is expected from linear acceleration while moving by hand."
          " Steady growth means rotation is being lost or mis-scaled.", ""]
    fig, ax = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    for i, c in enumerate(GYR):
        ax[0].plot(t_m, g[:, i], lw=0.6, label=c)
    for i, c in enumerate(ACC):
        ax[1].plot(t_m, acc[:, i], lw=0.6, label=c)
    for label, err in tilt.items():
        ax[2].plot(t_m, err, ".", ms=1.5, label=label)
    ax[0].set_ylabel("gyro (°/s)")
    ax[1].set_ylabel("accel (m/s²)")
    ax[2].set_ylabel("gravity mismatch (°)")
    ax[2].set_xlabel("device time (s)")
    for a_ in ax:
        a_.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "imu_motion.png"), dpi=110)
    plt.close(fig)

    # --- Clocks ---------------------------------------------------------------------------
    L += ["## Device clock", "",
          "- Drift of the camera clock relative to the host: %.0f ppm (still), %.0f ppm (motion)."
          % (clock_drift_ppm(still), clock_drift_ppm(motion)),
          "  (from the minimum-latency envelope of IMU arrivals; the SDK maps device time to host time,"
          " so a few hundred ppm is harmless for recording.)",
          "- All 4 fisheye images in a frame carry one device timestamp: the cameras are hardware-synchronised.", ""]

    # --- Cameras --------------------------------------------------------------------------
    if img_still is not None and img_motion is not None:
        L += ["## Fisheye cameras (640×480 each, 4 cameras, global shutter, grayscale)", "",
              "| cam | mean level (0–255) | saturated px % | black px % | sharpness still | sharpness motion "
              "| temporal noise (DN) |",
              "|---|---|---|---|---|---|---|"]
        low_motion = img_still["flow_px"].fillna(99) < 0.3
        for cam in sorted(img_still["cam"].unique()):
            s = img_still[img_still["cam"] == cam]
            mo = img_motion[img_motion["cam"] == cam]
            tn = s[low_motion[s.index]]["tnoise"]
            L.append("| %d | %.0f | %.2f | %.2f | %.0f | %.0f (min %.0f) | %.2f |" % (
                cam, s["mean"].mean(), s["sat_pct"].mean(), s["dark_pct"].mean(), s["sharpness"].median(),
                mo["sharpness"].median(), mo["sharpness"].quantile(0.02), tn.median()))
        L += ["",
              "- Sharpness = variance of Laplacian in the centre crop; higher is sharper. It depends on the scene,"
              " so compare between cameras and between still/motion, not against other cameras.",
              "- Temporal noise = std of frame-to-frame difference / √2 on still frames (includes any flicker).", ""]

        # Motion blur: sharpness vs angular rate.
        rate = np.degrees(np.linalg.norm(motion[GYR].to_numpy(), axis=1))
        m0 = img_motion[img_motion["cam"] == 0].copy()
        m0_t = (m0["edge_us"].to_numpy() - motion["edge_us"].iloc[0]) / 1e6
        m0["rate"] = np.interp(m0_t, motion["t"].to_numpy(), rate)
        # Normalise by neighbouring frames so scene content (texture) cancels out roughly.
        m0["rel_sharp"] = m0["sharpness"] / m0["sharpness"].rolling(9, center=True, min_periods=3).median()
        bins = [0, 30, 60, 100, 150, 200, 1000]
        m0["rbin"] = pd.cut(m0["rate"], bins)
        blur = m0.groupby("rbin", observed=True)["rel_sharp"].agg(["median", "count"])
        L += ["Motion blur (cam 0): sharpness relative to the 9 surrounding frames, by angular rate at capture"
              " (1.00 = as sharp as its neighbours):", "",
              "| angular rate (°/s) | frames | relative sharpness |", "|---|---|---|"]
        for k, r in blur.iterrows():
            L.append("| %s | %d | %.2f |" % (k, r["count"], r["median"]))
        L.append("")
        fastest = m0.loc[m0["rate"].idxmax()]
        L += ["- Fastest frame: %.0f °/s at t=%.1f s (frame %d), relative sharpness %.2f. To look at it:"
              " `scripts/export_frame.sh <motion_session> %d fastest_frame.png`."
              % (fastest["rate"], fastest["t"], fastest["frame"], fastest["rel_sharp"], fastest["frame"]), ""]

        # Time alignment.
        rows = []
        fig, ax = plt.subplots(1, 2, figsize=(14, 4.5))
        for cam in (0, 2):
            off, offs, corr, t_img, flow, grate = sync_offset(motion, img_motion, cam)
            rows.append((cam, off, np.nanmax(corr), corr[len(corr) // 2]))
            ax[1].plot(offs, corr, label="cam %d (peak %+.0f ms)" % (cam, off))
            if cam == 0:
                ax[0].plot(motion["t"], grate / np.nanpercentile(grate, 99), lw=0.6, label="|gyro| (norm.)")
                ax[0].plot(t_img, flow / np.nanpercentile(flow, 99), ".-", ms=2, lw=0.6, label="cam0 flow rate (norm.)")
        ax[0].set_xlabel("device time (s)")
        ax[0].legend()
        ax[0].set_title("Gyro rate vs image motion")
        ax[1].axvline(0, color="k", lw=0.8)
        ax[1].set_xlabel("offset applied to gyro (ms)")
        ax[1].set_ylabel("correlation")
        ax[1].legend()
        ax[1].set_title("Camera–IMU time alignment")
        fig.tight_layout()
        fig.savefig(os.path.join(out, "sync.png"), dpi=110)
        plt.close(fig)
        L += ["## Camera–IMU time alignment", "",
              "Optical-flow rate of each camera vs gyro rate, cross-correlated over ±150 ms:", "",
              "| cam | best offset (ms) | correlation at best | correlation at 0 ms |", "|---|---|---|---|"]
        for cam, off, cbest, c0 in rows:
            L.append("| %d | %+.0f | %.3f | %.3f |" % (cam, off, cbest, c0))
        L += ["", "Frames arrive only every 66–100 ms here, so treat this as ±10 ms resolution. "
              "See `sync.png`.", ""]

    L += ["Plots: `allan.png`, `imu_motion.png`, `sync.png`."]
    rep = "\n".join(L) + "\n"
    with open(os.path.join(out, "quality.md"), "w", encoding="utf-8") as f:
        f.write(rep)
    print(rep)
    print("written to", out)


if __name__ == "__main__":
    main()
