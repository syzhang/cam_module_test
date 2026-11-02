"""Per-frame image metrics for a cam_recorder session (needs only numpy + OpenCV).

Usage: python3 image_metrics.py <session_dir> [out_dir] [--flow-cams 0,2]

Writes <out_dir>/image_metrics.csv (default out_dir = session_dir) with one row per saved frame and camera:
    mean, std, sat_pct (>=250), dark_pct (<=5)  - exposure
    sharpness                                   - variance of Laplacian, centre crop
    tnoise                                      - temporal noise: std(frame - prev)/sqrt(2), centre crop
    flow_px, tracks, dt_s                       - median feature displacement vs previous frame (LK);
                                                  only for --flow-cams (the slow part; sync uses cams 0 and 2)
And <out_dir>/contact_sheet.png: all cameras at 6 moments of the recording.
"""
import argparse
import csv
import os

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("session")
ap.add_argument("out_dir", nargs="?")
ap.add_argument("--flow-cams", default="0,2", help="cameras to run feature tracking on ('all' for every camera)")
args = ap.parse_args()
session = args.session
out_dir = args.out_dir or session
os.makedirs(out_dir, exist_ok=True)
img_dir = os.path.join(session, "fisheye")

with open(os.path.join(session, "fisheye.csv")) as f:
    frames = [r for r in csv.DictReader(f) if r["saved"] == "1"]
n_cams = int(frames[0]["n_images"])
flow_cams = set(range(n_cams)) if args.flow_cams == "all" else {int(c) for c in args.flow_cams.split(",")}


def load(frame, cam):
    return cv2.imread(os.path.join(img_dir, "%08d_%d.pgm" % (int(frame), cam)), cv2.IMREAD_GRAYSCALE)


def centre(img):
    h, w = img.shape
    return img[h // 4: 3 * h // 4, w // 4: 3 * w // 4]


rows, prev, prev_t = [], {}, None
sheet_idx = set(np.linspace(0, len(frames) - 1, 6).astype(int).tolist())
sheet = []
for i, fr in enumerate(frames):
    t = int(fr["edge_us"]) / 1e6
    tiles = []
    for cam in range(n_cams):
        img = load(fr["frame"], cam)
        if img is None:
            continue
        c = centre(img)
        row = {
            "frame": fr["frame"], "edge_us": fr["edge_us"], "cam": cam,
            "mean": float(img.mean()), "std": float(img.std()),
            "sat_pct": 100.0 * float((img >= 250).mean()), "dark_pct": 100.0 * float((img <= 5).mean()),
            "sharpness": float(cv2.Laplacian(c, cv2.CV_64F).var()),
            "tnoise": "", "flow_px": "", "tracks": "", "dt_s": "",
        }
        if cam in prev:
            p = prev[cam]
            row["tnoise"] = float((c.astype(np.float32) - centre(p).astype(np.float32)).std() / np.sqrt(2))
            # Track corners (pyramidal LK copes with large motion; dense flow is dragged to ~0 by
            # textureless walls). Median displacement of good tracks = image motion in px.
            pts = cv2.goodFeaturesToTrack(p, 300, 0.01, 8) if cam in flow_cams else None
            if pts is not None and len(pts) >= 10:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(p, img, pts, None, winSize=(21, 21), maxLevel=4)
                fwd = st.ravel() == 1
                if fwd.sum() >= 10:
                    back, st2, _ = cv2.calcOpticalFlowPyrLK(img, p, nxt, None, winSize=(21, 21), maxLevel=4)
                    ok = fwd & (st2.ravel() == 1) & (np.linalg.norm((back - pts).reshape(-1, 2), axis=1) < 1.0)
                    if ok.sum() >= 10:
                        row["flow_px"] = float(np.median(np.linalg.norm((nxt - pts).reshape(-1, 2)[ok], axis=1)))
                        row["tracks"] = int(ok.sum())
            row["dt_s"] = t - prev_t
        prev[cam] = img
        rows.append(row)
        tiles.append(img)
    prev_t = t
    if i in sheet_idx and tiles:
        strip = np.hstack(tiles)
        cv2.putText(strip, "t=%.1fs" % (t - int(frames[0]["edge_us"]) / 1e6), (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, 255, 2)
        sheet.append(cv2.resize(strip, None, fx=0.5, fy=0.5))
    if i % 100 == 0:
        print("frame %d/%d" % (i, len(frames)), flush=True)

with open(os.path.join(out_dir, "image_metrics.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
cv2.imwrite(os.path.join(out_dir, "contact_sheet.png"), np.vstack(sheet))
print("wrote %d rows for %d frames x %d cams to %s" % (len(rows), len(frames), n_cams, out_dir))
