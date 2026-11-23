"""Capability check: Count (repetitions) on real RepCountA test videos with human counts.

Light model, no learned weights for the counter itself:
  - pixel signal: downscaled gray frames -> PCA -> most periodic component
  - pose signal (optional): MediaPipe Pose landmarks -> PCA -> most periodic component
Count = peaks on the band-limited signal with a minimum spacing of 0.6 x the autocorrelation period.
The 1 FPS control runs the identical counter on frames subsampled to 1 FPS (what a 1 FPS VLM sees).

usage: python count_repcount.py LANCE_DIR OUT.jsonl N SEED [--pose]
"""
import json
import pathlib
import random
import sys
import tempfile
import time

import cv2
import lance
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks


def frames_gray(path, size=64):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (size, size)).astype(np.float32).ravel())
    return fps, np.array(out)


POSE_MODEL = "/tmp/caplab/pose_landmarker_lite.task"  # sha256 59929e1d...574a (MediaPipe lite, float16)


def pose_series(path):
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=POSE_MODEL),
                                        running_mode=vision.RunningMode.VIDEO)
    rows, last, i = [], None, 0
    with vision.PoseLandmarker.create_from_options(opts) as pose:
        while True:
            ok, f = cap.read()
            if not ok:
                break
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            res = pose.detect_for_video(img, int(i * 1000 / fps))
            i += 1
            if res.pose_landmarks:
                last = np.array([[p.x, p.y] for p in res.pose_landmarks[0]]).ravel()
            rows.append(last if last is not None else np.zeros(66))
    return fps, np.array(rows)


def count_from_matrix(X, fps):
    """Most periodic PCA component of X (frames x features) -> repetition count.

    Pre-declared primary estimate: peaks spaced >= 0.6 x the dominant period.
    Secondary: dominant frequency x duration. Both are reported.
    """
    if len(X) < 8:
        return 0, None
    from scipy.signal import welch
    X = X - X.mean(axis=0)
    _, _, vt = np.linalg.svd(X, full_matrices=False)
    nyq = fps / 2
    lo_hz, hi_hz = 0.15, min(3.0, nyq * 0.9)
    if hi_hz <= lo_hz:
        return 0, None
    b, a = butter(2, [lo_hz / nyq, hi_hz / nyq], btype="band")
    best = None
    for k in range(min(3, vt.shape[0])):
        try:
            s = filtfilt(b, a, X @ vt[k])
        except ValueError:
            continue
        f, p = welch(s, fs=fps, nperseg=min(len(s), int(fps * 20)))
        band = (f >= lo_hz) & (f <= hi_hz)
        if not band.any() or p[band].sum() <= 0:
            continue
        i = int(np.argmax(p * band))
        purity = float(p[i] / p[band].sum())
        if best is None or purity > best[0]:
            best = (purity, s, f[i])
    if best is None:
        return 0, None
    purity, s, f_dom = best
    period = 1.0 / f_dom
    peaks, _ = find_peaks(s, distance=max(1, int(0.6 * period * fps)), prominence=0.3 * np.std(s))
    return int(len(peaks)), {"period_s": round(period, 3), "spectral_purity": round(purity, 3),
                             "freq_x_duration": int(round(f_dom * len(s) / fps))}

ds = lance.dataset(sys.argv[1])
rows = ds.to_table(columns=["video_id", "action_type", "count", "video_ext"]).to_pylist()
index = {r["video_id"]: i for i, r in enumerate(rows)}
rows = [r for r in rows if r["count"]]
random.Random(int(sys.argv[4])).shuffle(rows)
rows = sorted(rows[: int(sys.argv[3])], key=lambda r: r["video_id"])
use_pose = "--pose" in sys.argv
done = set()
if pathlib.Path(sys.argv[2]).exists():
    done = {json.loads(line)["video_id"] for line in open(sys.argv[2]) if line.strip()}
with open(sys.argv[2], "a") as out:
    for r in rows:
        if r["video_id"] in done:
            continue
        blob = ds.take_blobs("video_blob", indices=[index[r["video_id"]]])[0].read()
        with tempfile.NamedTemporaryFile(suffix="." + r["video_ext"]) as f:
            f.write(blob)
            f.flush()
            t0 = time.perf_counter()
            fps, G = frames_gray(f.name)
            full, info = count_from_matrix(G, fps)
            step = max(1, int(round(fps)))
            onefps, _ = count_from_matrix(G[::step], 1.0)
            row = {"video_id": r["video_id"], "action": r["action_type"], "gt": r["count"], "fps": round(fps, 2),
                   "frames": len(G), "pixel_full": full, "pixel_1fps": onefps, "info": info}
            if use_pose:
                pfps, P = pose_series(f.name)
                row["pose_full"], row["pose_info"] = count_from_matrix(P, pfps)
                row["pose_1fps"], _ = count_from_matrix(P[::step], 1.0)
            row["wall_s"] = round(time.perf_counter() - t0, 2)
        out.write(json.dumps(row) + "\n")
        out.flush()
        print(row, flush=True)
