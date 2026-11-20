"""Capability check: probability cloud (user rule -> risk with rise/decay/hysteresis) + memory, real video.

Data: MOTChallenge MOT17 training sequences (CC BY-NC-SA 3.0), mirror Morrison1025/MOT17@18fea9c.
Ground truth = human-annotated pedestrian boxes (gt.txt, class 1, visibility >= 0.25); a person is "in the
zone" when the bottom-centre of the box (foot point) is inside the user's zone rectangle.

User rule: "tell me when someone is at the shop entrance" (zone rectangle chosen from frame 1, before
any result was computed).

Light model: MediaPipe EfficientDet-Lite0 person detector on every frame (native 30 FPS).
Probability cloud: log-odds L_t = d * L_{t-1} + w * e_t - b, with
  e_t = sum over detections of exp(-dist^2 / 2 sigma^2), dist = foot point to zone (0 inside),
  d = exp(-dt / tau) (decay), p_t = sigmoid(L_t). Alarm ON when p >= 0.8, OFF when p <= 0.4 (hysteresis).
Baselines: the same detector with a naive threshold (p >= 0.5, no hysteresis), and the full model run
at 1 FPS (a 1 FPS observer).
Memory: every alarm ON/OFF is appended to GAMST's SemanticStateChain with time and evidence; the memory
questions ("how many times did someone come to the entrance?", "when was the last time?") are answered
from the chain only and checked against ground-truth episodes.

usage: python zone_risk.py SEQ_DIR X0 Y0 X1 Y1 OUT.json
"""
import json
import math
import pathlib
import sys

import cv2
import numpy as np

sys.path.insert(0, "/Users/jinminseong/Desktop/catch-your-mind")
from gamst.semantic_state import SemanticStateChain  # noqa: E402

DET_MODEL = "/tmp/caplab/efficientdet_lite0.tflite"
seq = pathlib.Path(sys.argv[1])
X0, Y0, X1, Y1 = map(float, sys.argv[2:6])
ini = dict(line.strip().split("=", 1) for line in open(seq / "seqinfo.ini") if "=" in line)
FPS, N = float(ini["frameRate"]), int(ini["seqLength"])
SIGMA, TAU, W, B = 60.0, 1.5, 0.9, 0.35
MIN_EPISODE_S = 0.5


def zone_dist(x, y):
    dx = max(X0 - x, 0, x - X1)
    dy = max(Y0 - y, 0, y - Y1)
    return math.hypot(dx, dy)


def gt_occupancy():
    occ = np.zeros(N, dtype=bool)
    for line in open(seq / "gt" / "gt.txt"):
        f, _, x, y, w, h, flag, cls, vis = line.strip().split(",")[:9]
        if int(flag) == 1 and int(cls) == 1 and float(vis) >= 0.25:
            fx, fy = float(x) + float(w) / 2, float(y) + float(h)
            if zone_dist(fx, fy) == 0:
                occ[int(f) - 1] = True
    return occ


def episodes(mask, fps, min_s=MIN_EPISODE_S):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j + 1 < len(mask) and mask[j + 1]:
                j += 1
            if (j - i + 1) / fps >= min_s:
                out.append((i / fps, (j + 1) / fps))
            i = j + 1
        else:
            i += 1
    return out


def detect_all():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    det = vision.ObjectDetector.create_from_options(vision.ObjectDetectorOptions(
        base_options=BaseOptions(model_asset_path=DET_MODEL), score_threshold=0.4, category_allowlist=["person"]))
    feet = []
    for k in range(1, N + 1):
        img = cv2.imread(str(seq / "img1" / f"{k:06d}.jpg"))
        res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        feet.append([(d.bounding_box.origin_x + d.bounding_box.width / 2, d.bounding_box.origin_y + d.bounding_box.height)
                     for d in res.detections])
    return feet


def run_cloud(feet, step=1):
    """Returns per-sample (t, p) and alarm intervals with hysteresis and with a naive threshold."""
    dt = step / FPS
    decay = math.exp(-dt / TAU)
    L, on, naive_on = -3.0, False, False
    trace, alarms, naive_toggles, start = [], [], 0, None
    for k in range(0, N, step):
        e = sum(math.exp(-zone_dist(x, y) ** 2 / (2 * SIGMA ** 2)) for x, y in feet[k])
        L = decay * L + (W * e - B) * dt * FPS / 3.0
        L = max(-6.0, min(6.0, L))
        p = 1 / (1 + math.exp(-L))
        t = k / FPS
        trace.append((round(t, 3), round(p, 4)))
        if not on and p >= 0.8:
            on, start = True, t
        elif on and p <= 0.4:
            on = False
            alarms.append((start, t))
        if (p >= 0.5) != naive_on:
            naive_on = not naive_on
            naive_toggles += 1
    if on:
        alarms.append((start, N / FPS))
    return trace, alarms, naive_toggles


def match(gt_eps, alarms, tol=1.0):
    """GT episode is detected if an alarm starts within [gt_start - tol, gt_end]; latency from GT start."""
    hits, lat, used = 0, [], set()
    for s, e in gt_eps:
        cand = [i for i, (a, _) in enumerate(alarms) if s - tol <= a <= e and i not in used]
        if cand:
            i = cand[0]
            used.add(i)
            hits += 1
            lat.append(alarms[i][0] - s)
    return {"gt_episodes": len(gt_eps), "detected": hits, "false_alarms": len(alarms) - len(used),
            "median_latency_s": round(float(np.median(lat)), 2) if lat else None}


def merge(eps, gap_s=1.0):
    """A visit tolerates <=1 s gaps (occlusions / box flicker in the annotation)."""
    out = []
    for s, e in eps:
        if out and s - out[-1][1] <= gap_s:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def frame_scores(alarms):
    on = np.zeros(N, dtype=bool)
    for s, e in alarms:
        on[int(s * FPS):int(e * FPS)] = True
    tp, fp, fn = int((on & occ).sum()), int((on & ~occ).sum()), int((~on & occ).sum())
    return {"frame_precision": round(tp / max(1, tp + fp), 3), "frame_recall": round(tp / max(1, tp + fn), 3)}


occ = gt_occupancy()
gt_eps = episodes(occ, FPS)
visits = merge(gt_eps)
feet = detect_all()
trace, alarms, naive_toggles = run_cloud(feet)
trace1, alarms1, _ = run_cloud(feet, step=int(FPS))

# memory: alarm events into GAMST's semantic state chain, questions answered from the chain only
chain = SemanticStateChain(max_updates=1024, retention_ms=24 * 3600 * 1000)
for s, e in alarms:
    chain.append("entrance", timestamp_ms=int(s * 1000), state={"zone": "entrance", "event": "enter"},
                 evidence_ids=[f"frame:{int(s * FPS) + 1:06d}"], sources=["video"], model_id="zone_risk", model_version="1")
    chain.append("entrance", timestamp_ms=int(e * 1000), state={"zone": "entrance", "event": "leave"},
                 evidence_ids=[f"frame:{int(e * FPS) + 1:06d}"], sources=["video"], model_id="zone_risk", model_version="1")
mem = chain.get("entrance", limit=256)["updates"]
enters = [u for u in mem if u["state"]["event"] == "enter"]
memory = {"q_how_many_visits": {"answer_from_chain": len(enters), "gt_raw_episodes": len(gt_eps),
                                "gt_visits_gap_le_1s": len(visits)},
          "q_last_visit_start_s": {"answer_from_chain": enters[-1]["timestamp_ms"] / 1000 if enters else None,
                                   "gt": visits[-1][0] if visits else None,
                                   "evidence": enters[-1]["evidence_ids"] if enters else None}}
summary = {"sequence": ini["name"], "fps": FPS, "frames": N, "zone": [X0, Y0, X1, Y1],
           "gt_occupied_frames": int(occ.sum()), "gt_raw_episodes": gt_eps, "gt_visits": visits,
           "cloud_30fps": {**match(visits, alarms), **frame_scores(alarms), "alarm_on_events": len(alarms)},
           "cloud_1fps": {**match(visits, alarms1), **frame_scores(alarms1), "alarm_on_events": len(alarms1)},
           "naive_threshold_toggles": naive_toggles, "hysteresis_toggles": 2 * len(alarms),
           "memory": memory,
           "params": {"sigma_px": SIGMA, "tau_s": TAU, "w": W, "b": B, "on": 0.8, "off": 0.4}}
pathlib.Path(sys.argv[6]).write_text(json.dumps({"summary": summary, "alarms": alarms, "trace": trace}, indent=1))
print(json.dumps(summary, indent=1))
