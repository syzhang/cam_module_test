"""Analyse a guided protocol recording (scripts/record_protocol.sh) phase by phase.

Usage: python protocol_analysis.py <session_dir> [--out DIR]   (default: <session_dir>/protocol_analysis)
Needs imu.csv, fisheye.csv, phases.csv and (for image sections) image_metrics.csv in the session dir.
Writes protocol_report.md + plots into <session>/protocol_analysis/.

Phase times in phases.csv are seconds from the start of recording; they are mapped onto the
camera clock via the first IMU sample, and 2 s are trimmed at each phase edge to absorb the
reaction time of the person following the cues.
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from module_quality import ACC, GYR, G, allan_dev, imu_static, load_img, load_imu, sync_offset  # noqa: E402

TRIM = 2.0


def phase_slice(df, t_col, p):
    return df[(df[t_col] >= p.start_s + TRIM) & (df[t_col] < p.end_s - TRIM)]


def delivery(imu, fe, p):
    """Received rate, loss vs the device clock grid, latency for one phase."""
    out = {}
    for name, d, period in (("imu", phase_slice(imu, "t", p), 0.002), ("fe", phase_slice(fe, "t", p), 1 / 30)):
        if len(d) < 3:
            out.update({name + "_hz": np.nan, name + "_loss": np.nan, name + "_lat": np.nan})
            continue
        e = np.sort(d["edge_us"].to_numpy()) / 1e6
        span = e[-1] - e[0]
        expected = span / period + 1
        out[name + "_hz"] = (len(d) - 1) / span
        out[name + "_loss"] = 100 * max(0.0, 1 - len(d) / expected)
        out[name + "_lat"] = 1e3 * np.median(d["arrival_s"] - d["host_s"])
    return out


def gravity_track(imu, bias_rad, g_mag, trapezoid=False):
    """Propagate gravity with the gyro over the whole run; mismatch vs accel at quasi-static moments.

    trapezoid=False holds the previous rate across a gap; True averages the rates at both ends,
    which recovers more of the rotation inside a gap.
    """
    t = imu["t"].to_numpy()
    acc = imu[ACC].to_numpy()
    w = imu[GYR].to_numpy() - bias_rad
    quasi = np.abs(np.linalg.norm(acc, axis=1) - g_mag) < 0.3
    first = np.where(quasi)[0][:100]
    gb = acc[first].mean(0)
    gb /= np.linalg.norm(gb)
    err = np.full(len(t), np.nan)
    for i in range(1, len(t)):
        wi = 0.5 * (w[i - 1] + w[i]) if trapezoid else w[i - 1]
        gb = gb - np.cross(wi, gb) * (t[i] - t[i - 1])
        gb /= np.linalg.norm(gb)
        if quasi[i]:
            err[i] = np.degrees(np.arccos(np.clip(np.dot(gb, acc[i] / np.linalg.norm(acc[i])), -1, 1)))
    return err


def detect_rests(imu, thresh_dps=2.0, min_s=5.0, trim_s=1.0):
    """Rest periods found from the data: smoothed |gyro| below thresh for at least min_s."""
    from module_quality import still_segments
    segs = still_segments(imu, thresh_dps, min_s)
    return [(a + trim_s, b - trim_s) for a, b in segs if b - a > 2 * trim_s + 1]


def rest_mismatch(imu, err, rests):
    return [np.nanmedian(err[(imu["t"] >= a) & (imu["t"] < b)]) for a, b in rests]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = a.session
    out = a.out or os.path.join(s, "protocol_analysis")
    os.makedirs(out, exist_ok=True)

    phases = pd.read_csv(os.path.join(s, "phases.csv"))
    imu = load_imu(s)
    fe = pd.read_csv(os.path.join(s, "fisheye.csv"))
    # Drop corrupted timestamps (seen once: 3.6e17 us).
    for d in (imu, fe):
        off = d["edge_us"] / 1e6 - d["arrival_s"]
        d.drop(d.index[(off - off.median()).abs() > 1.0], inplace=True)
    imu = imu.sort_values("edge_us").reset_index(drop=True)
    e0 = imu["edge_us"].iloc[0]
    imu["t"] = (imu["edge_us"] - e0) / 1e6
    fe = fe.sort_values("edge_us").reset_index(drop=True)
    fe["t"] = (fe["edge_us"] - e0) / 1e6
    img = load_img(s)
    if img is not None:
        img["t"] = (img["edge_us"] - e0) / 1e6
    end_t = imu["t"].iloc[-1]
    phases = phases[phases.start_s < end_t]

    L = ["# Protocol test: %s" % os.path.basename(os.path.normpath(s)), "",
         "Recorded %.0f s of IMU (%d samples) and %d fisheye frames. Phases trimmed by %.0f s at each edge."
         % (end_t, len(imu), len(fe), TRIM), ""]
    if end_t < phases.end_s.max() - 5:
        L += ["**Recording ended early at %.0f s** (device stopped or test aborted)." % end_t, ""]

    # --- Delivery per phase --------------------------------------------------------------
    rows = []
    for p in phases.itertuples():
        r = {"phase": p.phase, "t": "%d–%d" % (p.start_s, p.end_s)}
        r.update(delivery(imu, fe, p))
        seg = phase_slice(imu, "t", p)
        r["gyro_med_dps"] = np.median(np.degrees(np.linalg.norm(seg[GYR].to_numpy(), axis=1))) if len(seg) else np.nan
        rows.append(r)
    dl = pd.DataFrame(rows)
    L += ["## Delivery by phase", "",
          "| phase | time (s) | median |gyro| (°/s) | IMU Hz | IMU loss % | fisheye fps | fisheye loss % | fisheye latency (ms) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in dl.itertuples():
        L.append("| %s | %s | %.0f | %.0f | %.0f | %.1f | %.0f | %.0f |" % (
            r.phase, r.t, r.gyro_med_dps, r.imu_hz, r.imu_loss, r.fe_hz, r.fe_loss, r.fe_lat))
    still = dl.phase.str.startswith("still")
    L += ["", "- Average over still phases: IMU loss %.0f%%, fisheye loss %.0f%%, latency %.0f ms; "
          "over motion phases: IMU loss %.0f%%, fisheye loss %.0f%%, latency %.0f ms." % (
              dl[still].imu_loss.mean(), dl[still].fe_loss.mean(), dl[still].fe_lat.mean(),
              dl[~still].imu_loss.mean(), dl[~still].fe_loss.mean(), dl[~still].fe_lat.mean()), ""]

    # --- Rest periods: bias and gravity over 10 minutes ---------------------------------
    # Detected from the data: people start each step a few seconds after the cue, so the cue
    # times are only approximate.
    rest = []
    for k, (a0, a1) in enumerate(detect_rests(imu)):
        seg = imu[(imu["t"] >= a0) & (imu["t"] < a1)]
        if len(seg) < 100:
            continue
        p = pd.Series({"phase": "rest_%d" % (k + 1), "start_s": a0, "end_s": a1})
        st = imu_static(seg, p.phase)
        motion_in_rest = np.percentile(np.degrees(np.linalg.norm(seg[GYR].to_numpy() - np.radians(st["gyro_bias_dps"]), axis=1)), 95)
        rest.append((p, st, motion_in_rest))
    if rest:
        L += ["Rest periods detected from the data (|gyro| < 2°/s for ≥ 5 s, 1 s trimmed each side): "
              + ", ".join("%s %.0f–%.0f s" % (p.phase, p.start_s, p.end_s) for p, _, _ in rest) + ".", ""]
        ref = rest[0][1]
        L += ["## IMU in the rest periods", "",
              "| phase | at (s) | gyro bias x / y / z (°/s) | gyro noise x / y / z (°/s) | accel noise (mg) | |g| (m/s²) | "
              "gravity dir vs first rest (°) | 95th pct motion (°/s) |",
              "|---|---|---|---|---|---|---|---|"]
        for p, st, mot in rest:
            ang = np.degrees(np.arccos(np.clip(np.dot(st["acc_mean"], ref["acc_mean"]) /
                                               (np.linalg.norm(st["acc_mean"]) * np.linalg.norm(ref["acc_mean"])), -1, 1)))
            L.append("| %s | %d | %+.3f / %+.3f / %+.3f | %.3f / %.3f / %.3f | %.2f | %.4f | %.1f | %.2f |" % (
                (p.phase, p.start_s) + tuple(st["gyro_bias_dps"]) + tuple(st["gyro_std_dps"]) +
                (np.mean(st["acc_std"]) / G * 1e3, st["g_mag"], ang, mot)))
        biases = np.array([st["gyro_bias_dps"] for _, st, _ in rest])
        L += ["",
              "- Gyro bias spread across the %d rest periods (max − min): %.3f / %.3f / %.3f °/s (x/y/z)."
              % ((len(rest),) + tuple(biases.max(0) - biases.min(0))),
              "- A rest period whose 95th-percentile motion is above ~1°/s was probably not fully still"
              " (camera touched / table bumped); treat its bias as less reliable.", ""]

        # Allan deviation on the longest rest periods (start and end, 60 s each).
        fig, ax = plt.subplots(1, 2, figsize=(13, 4.5))
        for p, st, _ in rest:
            if p.end_s - p.start_s < 30:
                continue
            seg = imu[(imu["t"] >= p.start_s) & (imu["t"] < p.end_s)]
            tt = seg["t"].to_numpy() - seg["t"].iloc[0]
            taus = np.logspace(-2, np.log10(tt[-1] / 4), 20)
            for c, ls in zip(GYR, ("-", "--", ":")):
                ax[0].loglog(taus, allan_dev(tt, np.degrees(seg[c].to_numpy()), taus) * 3600, ls, label="%s %s" % (p.phase, c))
            for c, ls in zip(ACC, ("-", "--", ":")):
                ax[1].loglog(taus, allan_dev(tt, seg[c].to_numpy(), taus) / G * 1e6, ls, label="%s %s" % (p.phase, c))
        ax[0].set_ylabel("gyro Allan dev (°/h)")
        ax[1].set_ylabel("accel Allan dev (µg)")
        for a_ in ax:
            a_.set_xlabel("τ (s)")
            a_.grid(True, which="both", alpha=0.3)
            a_.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "allan_rest.png"), dpi=110)
        plt.close(fig)

        # Gravity consistency over the full run, with the first-rest bias.
        bias = np.radians(ref["gyro_bias_dps"])
        spans = [(p.start_s, p.end_s) for p, _, _ in rest]
        err = gravity_track(imu, bias, ref["g_mag"])
        err_raw = gravity_track(imu, np.zeros(3), ref["g_mag"])
        err_trap = gravity_track(imu, bias, ref["g_mag"], trapezoid=True)
        L += ["## Gyro integration over the whole run", "",
              "Gravity direction propagated with the gyro from the start, compared with the accelerometer in each"
              " rest period (all transport gaps included):", "",
              "| rest | at (s) | bias-corrected | bias-corrected, trapezoid across gaps | raw gyro |", "|---|---|---|---|---|"]
        for (p, st, _), e1, e2, e3 in zip(rest, rest_mismatch(imu, err, spans), rest_mismatch(imu, err_trap, spans),
                                         rest_mismatch(imu, err_raw, spans)):
            L.append("| %s | %.0f | %.1f° | %.1f° | %.1f° |" % (p.phase, p.start_s, e1, e2, e3))
        L += ["", "Rest periods have no linear acceleration, so this mismatch is pure orientation error from"
              " gyro bias/scale and from rotation lost in dropped samples.", ""]

        # How much of that error is the dropped samples? Drop even more (randomly) and extrapolate
        # the error back to zero loss.
        e_all = np.sort(imu["edge_us"].to_numpy())
        loss0 = 1 - len(imu) / ((e_all[-1] - e_all[0]) / 2000 + 1)
        rng = np.random.default_rng(0)
        pts = []
        for keep in (1.0, 0.8, 0.6, 0.4, 0.25):
            res = []
            for rep in range(1 if keep == 1.0 else 3):
                sub = imu if keep == 1.0 else imu[rng.random(len(imu)) < keep].reset_index(drop=True)
                e = gravity_track(sub, bias, ref["g_mag"], trapezoid=True)
                res.append(np.nanmean(rest_mismatch(sub, e, spans[1:])))
            pts.append((1 - keep * (1 - loss0), np.mean(res)))
        x, y = np.array(pts).T
        k, c0 = np.polyfit(x, y, 1)
        L += ["Effect of sample loss (received samples thinned further at random, trapezoid integration,"
              " mean mismatch over rests 2…%d):" % len(rest), "",
              "| effective IMU loss | mean mismatch |", "|---|---|"]
        L += ["| %.0f%% | %.1f° |" % (100 * xi, yi) for xi, yi in pts]
        at_obs = c0 + k * loss0
        if c0 <= 0.1 * at_obs:
            verdict = ("the line reaches ~0° at 0% loss, so essentially all of it comes from dropped samples;"
                       " the gyro's own contribution is below what this test can resolve (a few degrees).")
        else:
            verdict = ("so about %.0f%% of it comes from dropped samples and ~%.0f° from the gyro itself"
                       " (bias change, scale/axis error) or the bias estimate." % (100 * k * loss0 / at_obs, c0))
        L += ["", "- Linear fit: mismatch ≈ %.1f° + %.1f° × loss. At the observed %.0f%% loss the mean mismatch is"
              " %.0f°; %s Random thinning is not identical to real transport gaps (those come in bursts), so treat"
              " this as an estimate." % (c0, k, 100 * loss0, at_obs, verdict), ""]
        fig, ax_ = plt.subplots(figsize=(6, 4))
        ax_.plot(100 * x, y, "o")
        xx = np.linspace(0, 1, 50)
        ax_.plot(100 * xx, c0 + k * xx, "--")
        ax_.set_xlabel("effective IMU loss (%)")
        ax_.set_ylabel("mean gravity mismatch at rests (°)")
        ax_.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "loss_vs_error.png"), dpi=110)
        plt.close(fig)

    # --- Motion blocks (between detected rests) ------------------------------------------
    # The person starts each step late, so use the data: everything between two rests is one block,
    # labelled with the cue steps that overlap it most.
    bounds = [p.end_s for p, _, _ in rest] if rest else [0.0]
    starts = [p.start_s for p, _, _ in rest][1:] + [end_t]
    blocks = []
    for a0, a1 in zip(bounds, starts):
        if a1 - a0 < 5:
            continue
        ov = phases[(phases.end_s > a0) & (phases.start_s < a1) & ~phases.phase.str.startswith("still")]
        blocks.append(("%s" % "+".join(ov.phase) if len(ov) else "motion", a0, a1))

    def cam_stats(t0, t1):
        if img is None:
            return np.nan, np.nan
        mi = img[(img.cam == 0) & (img.t >= t0) & (img.t < t1)]
        return mi["tracks"].median(), mi["flow_px"].median()

    L += ["## Motion blocks", "",
          "Each block is the motion between two detected rest periods (cue steps it covers in brackets).", "",
          "| block | time (s) | median / peak |gyro| (°/s) | gyro axis share x / y / z | peak |accel| (g) | "
          "tracks/frame | image motion (px/frame) |",
          "|---|---|---|---|---|---|---|"]
    for label, a0, a1 in blocks:
        seg = imu[(imu.t >= a0) & (imu.t < a1)]
        g = np.degrees(seg[GYR].to_numpy())
        share = np.sqrt((g ** 2).mean(0))
        share = share / share.sum()
        tr, fl = cam_stats(a0, a1)
        L.append("| [%s] | %.0f–%.0f | %.0f / %.0f | %.0f%% / %.0f%% / %.0f%% | %.2f | %.0f | %.1f |" % (
            label, a0, a1, np.median(np.linalg.norm(g, axis=1)), np.linalg.norm(g, axis=1).max(),
            *(100 * share), np.linalg.norm(seg[ACC].to_numpy(), axis=1).max() / G, tr, fl))
    L.append("")

    # Axis mapping from the strongest single-axis 3 s windows in the rotation blocks.
    win = []
    for t0 in np.arange(0, end_t - 3, 1.0):
        seg = imu[(imu.t >= t0) & (imu.t < t0 + 3)]
        if len(seg) < 100:
            continue
        g = np.degrees(seg[GYR].to_numpy())
        rms = np.sqrt((g ** 2).mean(0))
        if rms.sum() > 60:
            win.append(rms / rms.sum())
    if win:
        win = np.array(win)
        purest = [win[:, i].max() for i in range(3)]
        L += ["- Purest single-axis rotation found in any 3 s window: x %.0f%%, y %.0f%%, z %.0f%% of the rotation"
              " on that axis. An axis that never dominates was not rotated cleanly on its own." % tuple(100 * np.array(purest)), ""]

    # Motion blur: sharpness relative to neighbouring frames, by angular rate.
    if img is not None:
        rate = np.degrees(np.linalg.norm(imu[GYR].to_numpy(), axis=1))
        m0 = img[img.cam == 0].sort_values("t").copy()
        m0["rate"] = np.interp(m0["t"], imu["t"], rate)
        m0["rel_sharp"] = m0["sharpness"] / m0["sharpness"].rolling(9, center=True, min_periods=3).median()
        m0["rbin"] = pd.cut(m0["rate"], [0, 30, 60, 100, 150, 200, 300, 1000])
        blur = m0.groupby("rbin", observed=True)["rel_sharp"].agg(["median", "count"])
        L += ["## Motion blur (cam 0)", "",
              "Sharpness relative to the 9 surrounding frames (cancels scene changes), by angular rate at capture:", "",
              "| angular rate (°/s) | frames | relative sharpness |", "|---|---|---|"]
        L += ["| %s | %d | %.2f |" % (k_, r["count"], r["median"]) for k_, r in blur.iterrows()]
        L.append("")

    # --- Image–IMU time alignment ----------------------------------------------------------
    if img is not None:
        def offset_in(t0, t1, cam):
            d = imu[(imu.t >= t0) & (imu.t < t1)].copy()
            m = img[(img.t >= t0) & (img.t < t1)]
            if len(d) < 200 or len(m) < 40:
                return None
            d["t"] = (d["edge_us"] - d["edge_us"].iloc[0]) / 1e6
            try:
                off, _, corr, *_ = sync_offset(d, m, cam)
            except Exception:
                return None
            return off, np.nanmax(corr)

        L += ["## Image–IMU time alignment", "",
              "Gyro rate vs feature-tracked image motion, cross-correlated over ±150 ms (positive = gyro shifted later).", "",
              "| window | cam 0 offset (corr) | cam 2 offset (corr) |", "|---|---|---|"]
        for label, a0, a1 in [("whole run", 0, end_t)] + [("[%s]" % b[0], b[1], b[2]) for b in blocks]:
            cells = []
            for cam in (0, 2):
                r = offset_in(a0, a1, cam)
                cells.append("%+.0f ms (%.2f)" % r if r else "–")
            L.append("| %s | %s | %s |" % (label, cells[0], cells[1]))

        # Sliding 30 s windows: is the offset stable over the run?
        slide = []
        for t0 in np.arange(0, end_t - 30, 15):
            for cam in (0, 2):
                r = offset_in(t0, t0 + 30, cam)
                if r and r[1] > 0.8:
                    slide.append((t0 + 15, cam, r[0], r[1]))
        if slide:
            sl = pd.DataFrame(slide, columns=["t", "cam", "off", "corr"])
            L += ["", "- Sliding 30 s windows with correlation > 0.8 (%d windows): offset mean %+.1f ms, std %.1f ms,"
                  " range %+.0f…%+.0f ms. No drift over time means image and IMU timestamps stay locked together."
                  % (len(sl), sl.off.mean(), sl.off.std(), sl.off.min(), sl.off.max()), ""]
            fig, ax_ = plt.subplots(figsize=(10, 3.5))
            for cam in (0, 2):
                s_ = sl[sl.cam == cam]
                ax_.plot(s_.t, s_.off, "o-", label="cam %d" % cam)
            ax_.axhline(0, color="k", lw=0.8)
            ax_.set_xlabel("time (s), centre of 30 s window")
            ax_.set_ylabel("image–IMU offset (ms)")
            ax_.set_ylim(-30, 30)
            ax_.grid(alpha=0.3)
            ax_.legend()
            fig.tight_layout()
            fig.savefig(os.path.join(out, "sync_over_time.png"), dpi=110)
            plt.close(fig)
        L.append("")

    # --- Overview plot ----------------------------------------------------------------------
    fig, ax = plt.subplots(4, 1, figsize=(15, 11), sharex=True)
    ax[0].plot(imu.t, np.degrees(np.linalg.norm(imu[GYR].to_numpy(), axis=1)), lw=0.4)
    ax[0].set_ylabel("|gyro| (°/s)")
    ax[1].plot(imu.t, np.linalg.norm(imu[ACC].to_numpy(), axis=1), lw=0.4)
    ax[1].set_ylabel("|accel| (m/s²)")
    lat = (fe.arrival_s - fe.host_s) * 1e3
    ax[2].plot(fe.t, lat, ".", ms=1.5)
    ax[2].set_ylabel("fisheye latency (ms)")
    if rest:
        ax[3].plot(imu.t, err, ".", ms=1, label="bias-corrected")
        ax[3].plot(imu.t, err_raw, ".", ms=1, label="raw gyro", alpha=0.5)
        ax[3].legend(loc="upper left")
    ax[3].set_ylabel("gravity mismatch (°)")
    ax[3].set_xlabel("time (s)")
    for p, _, _ in rest:
        for a_ in ax:
            a_.axvspan(p.start_s, p.end_s, color="green", alpha=0.1)
    for p in phases.itertuples():
        ax[0].axvline(p.start_s, color="grey", lw=0.5, ls=":")
        ax[0].text(p.start_s + 1, ax[0].get_ylim()[1] * 0.9, p.phase, fontsize=7, rotation=90, va="top")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "overview.png"), dpi=110)
    plt.close(fig)

    L += ["Plots: `overview.png` (green = detected rest periods, dotted = cue times), `allan_rest.png`, `loss_vs_error.png`, `sync_over_time.png`."]
    rep = "\n".join(L) + "\n"
    with open(os.path.join(out, "protocol_report.md"), "w", encoding="utf-8") as f:
        f.write(rep)
    print(rep)
    print("written to", out)


if __name__ == "__main__":
    main()
