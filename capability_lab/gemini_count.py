"""VLM reference for the Count capability: Gemini 3.1 Pro (Vertex) counts repetitions in the same videos.

Runs at Gemini's default video sampling (1 FPS) and at a dense setting (FPS given on the command line).
Auth: the local gcloud user token with the optimum-zone quota project (no key in files or argv).

usage: python gemini_count.py LANCE_DIR IDS_FROM.jsonl OUT.jsonl FPS [FPS ...]
"""
import base64
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import lance

MODEL = "gemini-3.1-pro-preview"
URL = ("https://aiplatform.googleapis.com/v1/projects/optimum-zone/locations/global/publishers/google/"
       f"models/{MODEL}:generateContent")
PROMPT = ("Count how many full repetitions of the exercise the person completes in this video. "
          "Reply with a single integer only.")


def token():
    return subprocess.run(["/opt/homebrew/share/google-cloud-sdk/bin/gcloud", "auth", "print-access-token"],
                          capture_output=True, text=True, check=True).stdout.strip()


def ask(video, fps, tok):
    part = {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(video).decode()}}
    if fps:
        part["videoMetadata"] = {"fps": fps}
    body = {"contents": [{"role": "user", "parts": [part, {"text": PROMPT}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                                 "thinkingConfig": {"thinkingLevel": "low"},
                                 "mediaResolution": "MEDIA_RESOLUTION_LOW"}}
    for attempt in range(5):
        req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + tok, "x-goog-user-project": "optimum-zone",
            "Content-Type": "application/json"})
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = json.load(r)
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            return text.strip(), data.get("usageMetadata", {}), time.time() - t
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < 4:
                time.sleep(5 * 2 ** attempt)
                continue
            raise
        except (TimeoutError, urllib.error.URLError):
            if attempt < 4:
                time.sleep(5 * 2 ** attempt)
                continue
            raise


ds = lance.dataset(sys.argv[1])
meta = ds.to_table(columns=["video_id"]).column("video_id").to_pylist()
index = {v: i for i, v in enumerate(meta)}
ids = [json.loads(line) for line in open(sys.argv[2])]
fps_list = [float(x) if x != "default" else None for x in sys.argv[4:]]
out_path = sys.argv[3]
done = set()
try:
    done = {json.loads(line)["video_id"] for line in open(out_path) if line.strip()}
except FileNotFoundError:
    pass
with open(out_path, "a") as out:
    for row in ids:
        if row["video_id"] in done:
            continue
        tok = token()  # user tokens expire after 1 h
        blob = ds.take_blobs("video_blob", indices=[index[row["video_id"]]])[0].read()
        rec = {"video_id": row["video_id"], "gt": row["gt"]}
        for fps in fps_list:
            key = f"gemini_{'1fps_default' if fps is None else str(int(fps)) + 'fps'}"
            try:
                text, usage, lat = ask(blob, fps, tok)
            except Exception as exc:  # recorded per call, never silently dropped
                rec[key], rec[key + "_error"] = None, f"{type(exc).__name__}: {exc}"[:200]
                continue
            m = re.search(r"-?\d+", text)
            rec[key] = int(m.group()) if m else None
            rec[key + "_tokens"] = usage.get("promptTokenCount")
            rec[key + "_latency_s"] = round(lat, 2)
        out.write(json.dumps(rec) + "\n")
        out.flush()
        print(rec, flush=True)
