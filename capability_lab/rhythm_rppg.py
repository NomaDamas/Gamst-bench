"""Capability check: rhythm (heart rate from a phone camera) on real MCD-rPPG videos.

Data: MCD-rPPG (kyegorov/mcd_rppg @ bf59b3c, CC-BY-4.0). Phone camera (IriunWebcam), resting ("before")
and after 15 squats ("after"); ground truth = contact PPG synchronised per video frame (`ppg_sync`).

Light model, no learned weights:
  face ROI (MediaPipe BlazeFace short-range, re-detected every 30 frames) -> mean RGB per frame -> POS
  projection (Wang et al. 2017) -> 0.7-3.0 Hz band -> Welch peak -> bpm. Same window (first 60 s) for prediction
  and ground truth. The 1 FPS control runs the identical pipeline on the trace sampled at 1 Hz.

usage: python rhythm_rppg.py WORKDIR OUT.json N_SUBJECTS SEED
"""
import csv
import json
import pathlib
import random
import statistics
import sys
import urllib.request

import cv2
import numpy as np
from scipy.signal import butter, filtfilt, welch

REV = "bf59b3cd1414c2a510d83c3125f16bb87d469ebb"
BASE = f"https://huggingface.co/datasets/kyegorov/mcd_rppg/resolve/{REV}/"
WINDOW_S = 60.0
work = pathlib.Path(sys.argv[1])


def fetch(rel):
    out = work / rel
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(BASE + rel, out)
    return out


def bpm_from(sig, fs, lo=0.7, hi=3.0):
    nyq = fs / 2
    hi = min(hi, nyq * 0.95)
    if hi <= lo or len(sig) < fs * 8:
        return None
    b, a = butter(3, [lo / nyq, hi / nyq], btype="band")
    s = filtfilt(b, a, sig - np.mean(sig))
    f, p = welch(s, fs=fs, nperseg=min(len(s), int(fs * 16)), nfft=max(4096, len(s)))
    band = (f >= lo) & (f <= hi)
    return float(f[band][np.argmax(p[band])] * 60.0)


FACE_MODEL = "/tmp/caplab/blaze_face_short_range.tflite"  # sha256 b4578f35...152f


def rgb_trace(video):
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    det = vision.FaceDetector.create_from_options(
        vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=FACE_MODEL)))
    roi, out, i = None, [], 0
    while len(out) < int(WINDOW_S * fps):
        ok, f = cap.read()
        if not ok:
            break
        if roi is None or i % 30 == 0:
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
            if res.detections:
                bb = max(res.detections, key=lambda d: d.bounding_box.width * d.bounding_box.height).bounding_box
                x, y, w, h = bb.origin_x, bb.origin_y, bb.width, bb.height
                # standard rPPG ROI: face box interior (10% margins), more skin pixels -> better SNR
                roi = (max(0, x + w // 10), max(0, y + h // 10), int(w * 0.8), int(h * 0.8))
        if roi is not None:
            x, y, w, h = roi
            out.append(f[y:y + h, x:x + w].reshape(-1, 3).mean(axis=0)[::-1])  # RGB
        i += 1
    return fps, np.array(out)


def pos(rgb, fs):
    """Plane-orthogonal-to-skin projection with 1.6 s sliding windows."""
    n, w = len(rgb), int(1.6 * fs)
    h = np.zeros(n)
    P = np.array([[0, 1, -1], [-2, 1, 1]])
    for t in range(0, n - w):
        c = rgb[t:t + w] / (rgb[t:t + w].mean(axis=0) + 1e-9)
        s = P @ c.T
        q = s[0] + (s[0].std() / (s[1].std() + 1e-9)) * s[1]
        h[t:t + w] += q - q.mean()
    return h


rows_db = list(csv.DictReader(open(fetch("db.csv"))))
subjects = sorted({r["patient_id"] for r in rows_db if r["camera"] == "IriunWebcam"})
pick = sorted(random.Random(int(sys.argv[4])).sample(subjects, int(sys.argv[3])))
results = []
for pid in pick:
    for step in ("before", "after"):
        rec = next((r for r in rows_db if r["patient_id"] == pid and r["camera"] == "IriunWebcam"
                    and r["step"] == step), None)
        if rec is None:
            continue
        video, sync = fetch(rec["video"]), fetch(rec["ppg_sync"])
        fps, rgb = rgb_trace(video)
        # ppg_sync: one contact-PPG sample per video frame (col 0), so it shares the video frame rate
        ppg = np.loadtxt(sync)[: int(WINDOW_S * fps), 0]
        row = {"patient_id": pid, "step": step, "gt_bpm": bpm_from(ppg, fps), "fps": round(fps, 2),
               "frames": len(rgb), "db_pulse": float(rec["pulse"]) if rec["pulse"] else None}
        if len(rgb) > fps * 10:
            row["cam_bpm"] = bpm_from(pos(rgb, fps), fps)
            step1 = max(1, int(round(fps)))
            # 1 Hz sampling cannot represent 0.7-3 Hz (Nyquist 0.5 Hz): report what it would read
            row["cam_1fps_bpm"] = bpm_from(pos(rgb[::step1], 1.0), 1.0, lo=0.05, hi=0.5)
        results.append(row)
        print(row, flush=True)


def err(key):
    e = [r[key] - r["gt_bpm"] for r in results if r.get(key) is not None and r["gt_bpm"] is not None]
    if not e:
        return {"n": 0}
    return {"n": len(e), "mae_bpm": round(statistics.mean(abs(x) for x in e), 2),
            "within_5bpm": round(sum(abs(x) <= 5 for x in e) / len(e), 3),
            "within_10bpm": round(sum(abs(x) <= 10 for x in e) / len(e), 3)}


pairs = {}
for r in results:
    pairs.setdefault(r["patient_id"], {})[r["step"]] = r
rise = [(p["after"].get("cam_bpm", 0) > p["before"].get("cam_bpm", 0)) == (p["after"]["gt_bpm"] > p["before"]["gt_bpm"])
        for p in pairs.values() if "after" in p and "before" in p and p["after"].get("cam_bpm") and p["before"].get("cam_bpm")]
summary = {"dataset": f"MCD-rPPG kyegorov/mcd_rppg@{REV[:7]} (CC-BY-4.0), IriunWebcam (phone)",
           "window_s": WINDOW_S, "videos": len(results), "cam": err("cam_bpm"), "cam_1fps": err("cam_1fps_bpm"),
           "before_after_direction_agreement": {"n": len(rise), "agree": sum(rise)}}
pathlib.Path(sys.argv[2]).write_text(json.dumps({"summary": summary, "rows": results}, indent=1))
print(json.dumps(summary, indent=1))
