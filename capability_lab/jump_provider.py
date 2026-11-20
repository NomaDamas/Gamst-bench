"""Run GAMST's FlightPhysics provider (gamst/providers/flight.py) on the real TU Wien JumpMetric skeletons.

Same data and ground truth as jump_physics.py; the provider adds two-sample contact debouncing and the
ballistic parabola fit of the airborne foot clearance. Offsets are learned leave-one-subject-out.

usage: python jump_provider.py JUMPMETRIC_DIR OUT.json [STEP]   (STEP=30 -> 1 Hz control)
"""
import csv
import json
import pathlib
import statistics
import sys

sys.path.insert(0, "/Users/jinminseong/Desktop/catch-your-mind")
from gamst import SensorMetadata  # noqa: E402
from gamst.plugins import InputFrame  # noqa: E402
from gamst.providers.flight import FlightPhysics  # noqa: E402

root = pathlib.Path(sys.argv[1])
step = int(sys.argv[3]) if len(sys.argv) > 3 else 1


def ys(path):
    with open(path) as f:
        return [-float(r["y"]) / 1000.0 for r in csv.DictReader(f, delimiter=";")]  # Kinect y down -> up, metres


truth = {}
with open(root / "groundtruth.csv") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if float(r["height_measured"]) >= 0:
            truth[(int(r["id"]), int(r["jump"]))] = (float(r["height_measured"]), r["well_executed"] == "1")

rows = []
for (sid, jump), (gt_mm, good) in sorted(truth.items()):
    d = root / "depthcamera" / f"{sid:02d}" / f"j{jump}"
    fl, fr = ys(d / f"s{sid:02d}_j{jump}_foot_left.csv"), ys(d / f"s{sid:02d}_j{jump}_foot_right.csv")
    pel = ys(d / f"s{sid:02d}_j{jump}_pelvis.csv")
    n = min(len(fl), len(fr), len(pel))
    p = FlightPhysics(max_gap_ms=int(1000 * step / 30) + 50, baseline_s=0.5 if step == 1 else 1.0)
    jumps = []
    for k, i in enumerate(range(0, n, step)):
        out = p.process(InputFrame({"foot_height_m": min(fl[i], fr[i]), "body_height_m": pel[i]}, "video",
                                   int(i * 1000 / 30), sensor=SensorMetadata("kinect", "skeleton", k, stream_epoch=f"s{sid}j{jump}")))
        jumps += [e for e in out["events"] if e["event"] == "jump"]
    best = max(jumps, key=lambda e: e["flight_s"]) if jumps else None
    rows.append({"id": sid, "jump": jump, "gt_mm": gt_mm, "well_executed": good,
                 "flight_mm": best["height_flight_m"] * 1000 if best else None,
                 "rise_mm": best["rise_m"] * 1000 if best and "rise_m" in best else None,
                 "method": best["timing_method"] if best else None,
                 "fitted_g": best.get("fitted_gravity_m_s2") if best else None})

for key in ("flight_mm", "rise_mm"):
    for r in rows:
        others = [o[key] - o["gt_mm"] for o in rows if o["id"] != r["id"] and o[key] is not None]
        r[key + "_loso"] = None if r[key] is None or not others else r[key] - statistics.median(others)


def stats(key, subset):
    e = [r[key] - r["gt_mm"] for r in subset if r[key] is not None]
    if not e:
        return {"n": 0, "of": len(subset)}
    return {"n": len(e), "of": len(subset), "mae_mm": round(statistics.mean(abs(x) for x in e), 1),
            "sd_mm": round(statistics.pstdev(e), 1), "within_50mm": round(sum(abs(x) <= 50 for x in e) / len(e), 3)}


good = [r for r in rows if r["well_executed"]]
keys = ("flight_mm", "flight_mm_loso", "rise_mm", "rise_mm_loso")
summary = {"step": step, "well_executed": {k: stats(k, good) for k in keys},
           "ballistic_fit_share": round(sum(r["method"] == "ballistic_fit" for r in good) / len(good), 3),
           "fitted_g_median": statistics.median([r["fitted_g"] for r in good if r["fitted_g"]] or [0])}
pathlib.Path(sys.argv[2]).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
print(json.dumps(summary, indent=1))
