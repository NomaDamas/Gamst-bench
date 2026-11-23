"""Capability check: moment capture + physics (jump height) on the real TU Wien JumpMetric dataset.

Data (CC-BY-4.0, doi:10.48436/c0584-yqb91): 44 subjects x 5 countermovement jumps, Azure Kinect skeleton
at 30 Hz and 10 wearable 3-axis accelerometers at 100 Hz, ground-truth jump height `height_measured` (mm).
Jumps whose ground truth is missing (-1) are excluded.

Estimators (no learned weights; Kinect y axis points down):
  cam_takeoff_rise  moment capture: takeoff = last frame before both foot joints rise >20 mm; height =
                    pelvis(takeoff) - pelvis(apex)                                      [primary]
  cam_flight        flight time T while both feet are >20 mm up, h = g T^2 / 8
  imu_flight        neck/chest/hip accelerometer free fall (50 ms median |a| < 0.5 g), h = g T^2 / 8
  cam_1fps          pelvis rise above standing height using only 1 Hz samples (a 1 FPS observer)
Each estimator is also reported with a leave-one-subject-out constant offset (calibration learned only
from the other 43 subjects), which removes a fixed setup bias without seeing the test subject.

usage: python jump_physics.py JUMPMETRIC_DIR OUT.json
"""
import csv
import json
import pathlib
import statistics
import sys

import numpy as np
from scipy.signal import medfilt

G = 9.80665
root = pathlib.Path(sys.argv[1])


def read_xyz(path):
    with open(path) as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    return np.array([[float(r[k]) for k in ("x", "y", "z")] for r in rows]) if rows else np.zeros((0, 3))


def read_acc(path):
    if not path.exists():
        return None, None
    with open(path) as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if not rows:
        return None, None
    t = np.array([float(r["t"]) for r in rows]) / 1000.0
    return t, np.linalg.norm(np.array([[float(r[k]) for k in ("x", "y", "z")] for r in rows]), axis=1)


def runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def flight_mm(T):
    return G * T ** 2 / 8 * 1000.0


def camera(foot_l, foot_r, pelvis, fps=30.0):
    n = min(len(foot_l), len(foot_r), len(pelvis))
    if n < 20:
        return None, None
    rise = np.stack([np.median(a[:15, 1]) - a[:n, 1] for a in (foot_l, foot_r)]).min(axis=0)
    apex = int(np.argmin(pelvis[:n, 1]))
    air = [r for r in runs(rise > 20.0) if r[0] <= apex <= r[1]]
    if not air:
        return None, None
    i, j = air[0]
    takeoff = max(0, i - 1)
    T = (j - i + 1) / fps
    return float(pelvis[takeoff, 1] - pelvis[apex, 1]), (flight_mm(T) if 0.15 <= T <= 1.0 else None)


def imu(t, mag):
    if t is None or len(t) < 20:
        return None
    sm = medfilt(mag, 5)
    best = None
    for i, j in runs(sm < 0.5):
        T = float(t[j] - t[i]) + 0.01
        if 0.15 <= T <= 1.0 and (best is None or T > best):
            best = T
    return None if best is None else flight_mm(best)


def one_fps(pelvis):
    p = pelvis[::30, 1]
    return float(np.median(pelvis[:15, 1]) - p.min()) if len(p) >= 2 else None


truth = {}
with open(root / "groundtruth.csv") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if float(r["height_measured"]) >= 0:
            truth[(int(r["id"]), int(r["jump"]))] = {"gt_mm": float(r["height_measured"]),
                                                     "well_executed": r["well_executed"] == "1"}

rows = []
for (sid, jump), gt in sorted(truth.items()):
    d = root / "depthcamera" / f"{sid:02d}" / f"j{jump}"
    w = root / "wearables" / f"{sid:02d}" / f"j{jump}"
    fl, fr = read_xyz(d / f"s{sid:02d}_j{jump}_foot_left.csv"), read_xyz(d / f"s{sid:02d}_j{jump}_foot_right.csv")
    pel = read_xyz(d / f"s{sid:02d}_j{jump}_pelvis.csv")
    rise, flight = camera(fl, fr, pel)
    acc = None
    for pos in ("neck", "chest", "hip_l"):
        acc = imu(*read_acc(w / f"s{sid:02d}_j{jump}_{pos}.csv"))
        if acc is not None:
            break
    rows.append({"id": sid, "jump": jump, **gt, "cam_takeoff_rise": rise, "cam_flight": flight,
                 "imu_flight": acc, "cam_1fps": one_fps(pel)})

KEYS = ("cam_takeoff_rise", "cam_flight", "imu_flight", "cam_1fps")
for key in KEYS:  # leave-one-subject-out constant offset
    for r in rows:
        others = [o[key] - o["gt_mm"] for o in rows if o["id"] != r["id"] and o[key] is not None]
        r[key + "_loso"] = None if r[key] is None or not others else r[key] - statistics.median(others)


def stats(key, subset):
    err = [r[key] - r["gt_mm"] for r in subset if r[key] is not None]
    if not err:
        return {"n": 0, "of": len(subset)}
    return {"n": len(err), "of": len(subset), "mean_err_mm": round(statistics.mean(err), 1),
            "sd_mm": round(statistics.pstdev(err), 1), "mae_mm": round(statistics.mean(abs(e) for e in err), 1),
            "within_30mm": round(sum(abs(e) <= 30 for e in err) / len(err), 3),
            "within_50mm": round(sum(abs(e) <= 50 for e in err) / len(err), 3)}


allk = [k for key in KEYS for k in (key, key + "_loso")]
good = [r for r in rows if r["well_executed"]]
summary = {"dataset": "TU Wien JumpMetric doi:10.48436/c0584-yqb91 (CC-BY-4.0)",
           "ground_truth": "height_measured (mm); missing (-1) excluded", "jumps": len(rows),
           "gt_mean_mm": round(statistics.mean(r["gt_mm"] for r in rows), 1),
           "all_valid": {k: stats(k, rows) for k in allk},
           "well_executed": {k: stats(k, good) for k in allk}}
pathlib.Path(sys.argv[2]).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
print(json.dumps(summary, indent=1))
