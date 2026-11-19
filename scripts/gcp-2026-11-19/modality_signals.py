"""Lightweight high-frequency modality plugins: video motion and audio onsets.

Reads the real episode clip (already bounded at the query cutoff) at its native
frame rate (no keyframe sampling) and 16 kHz mono audio. Emits typed GAMST
perception signals with absolute video timestamps and evidence IDs. No model
inference, no labels.

usage: python modality_signals.py EPISODES.jsonl OUT.jsonl
EPISODES.jsonl rows: {"id", "video" (clip), "offset_s" (clip start, absolute), "cutoff_s"}
"""
import json
import pathlib
import subprocess
import sys
import time

import numpy as np

W, H = 64, 36  # downscaled grayscale plane for motion energy


def probe_fps(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=avg_frame_rate", "-of", "csv=p=0", video],
                         capture_output=True, text=True, check=True).stdout.strip()
    num, den = out.split("/") if "/" in out else (out, "1")
    return float(num) / float(den or 1)


def video_motion(video, start, dur):
    """`start` is the absolute time of the clip's first frame."""
    fps = probe_fps(video)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(dur), "-i", video,
                          "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
    if len(frames) < 2:
        return fps, [], len(frames)
    energy = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    t = start + (np.arange(1, len(frames)) / fps)
    # causal baseline: median/MAD of the previous 5 s only (no future frames)
    w = max(4, int(5 * fps))
    base = np.empty_like(energy)
    spread = np.empty_like(energy)
    for k in range(len(energy)):
        past = energy[max(0, k - w):k] if k >= 4 else energy[:k + 1]
        base[k] = np.median(past) + 1e-3
        spread[k] = np.median(np.abs(past - base[k])) + 1e-3
    hot = energy > base + 6 * spread
    signals, i = [], 0
    while i < len(hot):  # contiguous motion bursts
        if hot[i]:
            j = i
            while j + 1 < len(hot) and hot[j + 1]:
                j += 1
            peak = int(i + np.argmax(energy[i:j + 1]))
            # emitted when the burst has ended (the plugin cannot know the offset earlier)
            signals.append({"name": f"video.motion_burst@{t[i]:.3f}", "modality": "video",
                            "plugin": "video.motion_energy", "timestamp_ms": int(t[j] * 1000),
                            "value": {"onset_s": round(float(t[i]), 3), "offset_s": round(float(t[j]), 3),
                                      "peak_s": round(float(t[peak]), 3),
                                      "peak_energy": round(float(energy[peak]), 2),
                                      "baseline": round(float(base[i]), 2)},
                            "evidence_ids": [f"frame:{t[i]:.3f}", f"frame:{t[peak]:.3f}", f"frame:{t[j]:.3f}"]})
            i = j + 1
        else:
            i += 1
    return fps, signals, len(frames)


def audio_onsets(video, start, dur, sr=16000, hop=160):
    proc = subprocess.run(["ffmpeg", "-v", "error", "-t", str(dur), "-i", video,
                           "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True)
    pcm = np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0
    if len(pcm) < hop * 4:
        return False, []
    n = len(pcm) // hop
    rms = np.sqrt((pcm[:n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-10)
    db = 20 * np.log10(rms)
    rise = np.diff(db, prepend=db[0])
    # causal noise floor: 20th percentile of the previous 5 s (500 hops) only
    floor = np.array([np.percentile(db[max(0, k - 500):k + 1], 20) for k in range(n)])
    hits = np.where((rise > 9) & (db > floor + 15))[0]
    signals, last = [], -10**9
    for k in hits:
        if k - last < 10:  # 100 ms refractory
            continue
        last = k
        ts = start + k * hop / sr
        signals.append({"name": f"audio.onset@{ts:.3f}", "modality": "audio", "plugin": "audio.energy_onset",
                        "timestamp_ms": int(ts * 1000),
                        "value": {"onset_s": round(ts, 3), "level_db": round(float(db[k]), 1),
                                  "rise_db": round(float(rise[k]), 1), "floor_db": round(float(floor[k]), 1)},
                        "evidence_ids": [f"audio:{ts:.3f}"]})
    return True, signals


episodes = [json.loads(line) for line in open(sys.argv[1])]
out = pathlib.Path(sys.argv[2])
with out.open("w") as sink:
    for ep in episodes:
        start = float(ep["offset_s"])
        dur = max(0.5, float(ep["cutoff_s"]) - start)
        t0 = time.perf_counter()
        fps, motion, nframes = video_motion(ep["video"], start, dur)
        has_audio, onsets = audio_onsets(ep["video"], start, dur)
        sink.write(json.dumps({"id": ep["id"], "source_fps": fps, "frames_read": nframes,
                               "has_audio": has_audio, "signals": motion + onsets,
                               "wall_s": round(time.perf_counter() - t0, 3)}) + "\n")
        print(ep["id"], fps, nframes, len(motion), len(onsets), flush=True)
