"""GAMST-HF benchmark on real StreamArena (YouTube) episodes.

Subcommands (all resumable, one JSONL row per episode):
  prep      cut each episode window [start_s, cutoff_s) from the source mp4 and upload to GCS
  gate      anti-shortcut controls with the reference VLM (1FPS, first+last, shuffled)
  arm NAME  run one arm: qwen_small | streamingvlm | strong | gemini_live | gamst
  judge     StreamArena judge prompts + Pro timing rule over every arm output

Labels are the human StreamArena annotations; nothing here writes labels.
Proactive (T1) protocol = StreamArena: silent in [ask, ref), first alert must
start within [ref-0.5, ref+2.0] video seconds. Decision time is the video
timestamp of the polled window end; compute latency is reported separately.
"""
import asyncio
import base64
import json
import os
import pathlib
import random
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(os.environ.get("HF_ROOT", "/srv/hf"))
VIDEOS = pathlib.Path(os.environ.get("SA_VIDEOS", "/srv/data/streamarena/videos"))
GCS = os.environ.get("HF_GCS", "gs://gamst-bench-datasets-optimum-zone/gamst-hf/2026-11-19/clips")
PROJECT = "optimum-zone"
STRONG = os.environ.get("HF_STRONG", "gemini-3.1-pro-preview")
JUDGE = os.environ.get("HF_JUDGE", "gemini-3.1-pro-preview")  # Vertex AI, StreamArena judge prompts
# gemini-3.1-flash-live-preview is listed but Live connect returns 1008 "not found" for this
# project in every tested region (2026-11-19); the GA native-audio Live model is used.
LIVE = os.environ.get("HF_LIVE", "gemini-live-2.5-flash-native-audio")
LOCAL = os.environ.get("HF_LOCAL", "http://127.0.0.1:8080/v1")
SVLM_STATE = ROOT / "streamingvlm_state.jsonl"
SIGNALS = ROOT / "modality_signals.jsonl"

QA_SYS = ("You are watching a live video stream. Answer the user's question about what was "
          "seen or heard up to now. Reply in exactly this format:\n"
          "ANSWER: <short answer> | EVIDENCE_T: <video seconds where the evidence was seen or heard, "
          "comma separated>")


def split_answer(text):
    """(answer, [evidence seconds]) from 'ANSWER: ... | EVIDENCE_T: ...'; lenient."""
    import re
    text = text or ""
    m = re.search(r"EVIDENCE_T\s*:\s*(.*)$", text, re.I | re.S)
    ev = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", m.group(1))] if m else []
    ans = text[:m.start()] if m else text
    ans = re.sub(r"^\s*ANSWER\s*:\s*", "", ans.strip(), flags=re.I).strip().rstrip("|").strip()
    return ans, ev


PRO_SYS = ("You are watching a live video stream. The user asked you to notify them when a "
           "specific event happens. If it has NOT happened yet in the latest frames, reply exactly "
           "WAIT. If it is happening now, reply with the short notification only.")


def sid(ep):
    return ep["id"].replace("#", "__q")


def episodes():
    return [json.loads(line) for line in open(ROOT / "candidates.jsonl")]


def done_ids(path):
    """Ids with a successful row; errored rows are retried and the newest row per id wins."""
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.open() if line.strip()]
    return {r["id"] for r in rows if not r.get("error")}


def append(path, row):
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def source_mp4(video_id):
    return VIDEOS / video_id / f"{video_id}.mp4"


def clip_path(ep):
    return ROOT / "clips" / f"{sid(ep)}.mp4"


# ---------------------------------------------------------------- media
def frames(ep, fps, t0=None, t1=None, width=448):
    """JPEG frames from the episode clip, (abs_t, b64). Never reads past cutoff."""
    t0 = ep["start_s"] if t0 is None else t0
    t1 = ep["cutoff_s"] if t1 is None else min(t1, ep["cutoff_s"])
    rel0 = max(0.0, t0 - ep["start_s"])
    dur = max(0.05, t1 - t0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{rel0:.3f}", "-t", f"{dur:.3f}",
                          "-i", str(clip_path(ep)), "-vf", f"fps={fps},scale={width}:-2",
                          "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "4", "-"],
                         capture_output=True, check=True).stdout
    out, i = [], 0
    for part in raw.split(b"\xff\xd8")[1:]:
        out.append((round(t0 + i / fps, 3), base64.b64encode(b"\xff\xd8" + part).decode()))
        i += 1
    return out


def cap(items, n):
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(k * step)] for k in range(n)]


# ---------------------------------------------------------------- local VLM (vLLM)
def local_chat(model, system, user_text, frame_list, max_tokens=96, sampling=None):
    content = []
    for t, b64 in frame_list:
        content.append({"type": "text", "text": f"[t={t:.1f}s]"})
        content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}})
    content.append({"type": "text", "text": user_text})
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, **(sampling or {}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    req = urllib.request.Request(LOCAL + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"].strip(), data.get("usage"), time.time() - t


def served_model():
    with urllib.request.urlopen(LOCAL + "/models", timeout=30) as r:
        return json.load(r)["data"][0]["id"]


# ---------------------------------------------------------------- Gemini (Vertex)
_client = None


def genai_client(location="global"):
    global _client
    from google import genai
    if _client is None:
        _client = genai.Client(vertexai=True, project=PROJECT, location=location)
    return _client


def usage_dict(resp):
    u = getattr(resp, "usage_metadata", None)
    if u is None:
        return None
    return {k: getattr(u, k, None) for k in ("prompt_token_count", "candidates_token_count",
                                             "thoughts_token_count", "total_token_count")}


def gemini(model, system, parts, max_tokens=256, thinking="low"):
    from google.genai import types
    cfg = types.GenerateContentConfig(system_instruction=system, temperature=0,
                                      max_output_tokens=max_tokens + 4096,
                                      thinking_config=types.ThinkingConfig(thinking_level=thinking),
                                      media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW)
    for attempt in range(6):
        t = time.time()
        try:
            resp = genai_client().models.generate_content(model=model, contents=parts, config=cfg)
            return (resp.text or "").strip(), usage_dict(resp), time.time() - t
        except Exception:  # 429/5xx: bounded retry, then recorded as error by the caller
            if attempt == 5:
                raise
            time.sleep(min(60, 4 * 2 ** attempt) + random.random())


def video_part(ep, t0, t1, fps, audio=True):
    from google.genai import types
    base = GCS if audio else GCS + "_noaudio"
    return types.Part(file_data=types.FileData(file_uri=f"{base}/{sid(ep)}.mp4", mime_type="video/mp4"),
                      video_metadata=types.VideoMetadata(start_offset=f"{max(0.0, t0 - ep['start_s']):.2f}s",
                                                         end_offset=f"{min(t1, ep['cutoff_s']) - ep['start_s']:.2f}s",
                                                         fps=fps))


def noaudio_clip(ep):
    """Same clip with the audio track removed (stream copy), uploaded beside the AV clip."""
    out = ROOT / "clips_noaudio" / f"{sid(ep)}.mp4"
    if not out.exists():
        out.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip_path(ep)), "-c:v", "copy", "-an", str(out)],
                       check=True)
        subprocess.run(["gcloud", "storage", "cp", "-q", str(out), f"{GCS}_noaudio/{out.name}"], check=True)


def image_parts(frame_list):
    from google.genai import types
    parts = []
    for t, b64 in frame_list:
        parts.append(types.Part(text=f"[t={t:.1f}s]"))
        parts.append(types.Part(inline_data=types.Blob(data=base64.b64decode(b64), mime_type="image/jpeg")))
    return parts


# ---------------------------------------------------------------- prep
def cmd_prep():
    (ROOT / "clips").mkdir(parents=True, exist_ok=True)
    for ep in episodes():
        out = clip_path(ep)
        if not out.exists():
            src = source_mp4(ep["video_id"])
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ep["start_s"]), "-i", str(src),
                            "-t", str(ep["cutoff_s"] - ep["start_s"]), "-vf", "scale=-2:480",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-g", "15",
                            "-c:a", "aac", "-ar", "16000", "-ac", "1", str(out)], check=True)
        print("clip", ep["id"], flush=True)
    subprocess.run(["gcloud", "storage", "rsync", str(ROOT / "clips"), GCS], check=True)


# ---------------------------------------------------------------- polling protocol (T1)
def poll_proactive(ep, decide, period=1.0, lookback=8.0, fps=2):
    """Poll every `period` video seconds from ask to ref+2; stop at first non-WAIT."""
    polls, t = [], ep["start_s"] + period
    end = ep["ref_sec"] + 2.0
    while t <= end + 1e-6:
        text, usage, lat = decide(max(ep["start_s"], t - lookback), t, fps)
        polls.append({"t": round(t, 2), "text": text, "usage": usage, "latency_s": round(lat, 3)})
        if text and not text.upper().startswith("WAIT"):
            return {"answer": text, "speak_t": round(t, 2), "polls": polls}
        t += period
    return {"answer": "", "speak_t": None, "polls": polls}


def question_text(ep):
    # same time anchor for every arm: clip/stream second 0 is video t=start_s
    return (f"[The stream you see starts at video t={ep['start_s']}s; clip time 0 = t={ep['start_s']}s.]\n"
            f"User (at t={ep['ask_sec']}s): {ep['question']}")


# ---------------------------------------------------------------- gate
def cmd_gate():
    import concurrent.futures
    import threading
    model = served_model()
    out = ROOT / "gate.jsonl"
    done = done_ids(out)
    lock = threading.Lock()

    def one(ep):
        row = {"id": ep["id"], "gate_model": model}
        try:
            if ep["scoring"] == "qa":
                onefps = cap(frames(ep, 1), 128)
                row["1fps_frames"] = len(onefps)
                row["1fps"] = local_chat(model, QA_SYS, question_text(ep), onefps)[0]
                fl = frames(ep, 2)
                row["first_last"] = local_chat(model, QA_SYS, question_text(ep), [fl[0], fl[-1]])[0]
                shuf = cap(fl, 128)
                order = random.Random(ep["id"]).sample(range(len(shuf)), len(shuf))
                row["shuffled"] = local_chat(model, QA_SYS, question_text(ep),
                                             [(shuf[k][0], shuf[j][1]) for k, j in enumerate(order)])[0]
            else:
                def decide(t0, t1, fps):
                    return local_chat(model, PRO_SYS, question_text(ep) + "\nWAIT or notification?",
                                      frames(ep, 1, t0, t1))
                row["1fps"] = poll_proactive(ep, decide, period=1.0, lookback=8.0, fps=1)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"[:300]
        with lock:
            append(out, row)
        print("gate", ep["id"], row.get("error"), flush=True)
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        list(pool.map(one, [e for e in episodes() if e["id"] not in done]))


# ---------------------------------------------------------------- arms
def arm_local(name, fps=2, max_frames=128):
    model = served_model()
    # StreamingVLM is a live-commentary checkpoint: greedy decoding collapses to "... ...", so it
    # runs with its upstream decoding defaults (temperature 0.9, repetition penalty 1.05), seeded.
    sampling = {"temperature": 0.9, "repetition_penalty": 1.05, "seed": 42} if name == "streamingvlm" else None

    def qa(ep):
        fl = cap(frames(ep, fps), max_frames)
        text, usage, lat = local_chat(model, QA_SYS, question_text(ep), fl, sampling=sampling)
        return {"answer": text, "usage": usage, "latency_s": lat, "frames": len(fl), "calls": 1}

    def pro(ep):
        r = poll_proactive(ep, lambda t0, t1, f: local_chat(model, PRO_SYS, question_text(ep) +
                                                            "\nWAIT or notification?", frames(ep, f, t0, t1),
                                                            sampling=sampling),
                           period=1.0, lookback=8.0, fps=fps)
        r["calls"] = len(r["polls"])
        return r
    return model, qa, pro


def arm_strong(audio=True):
    """audio=False is the AV ablation: identical call on the audio-stripped clip (T3 only)."""
    from google.genai import types

    def qa(ep):
        if not audio:
            noaudio_clip(ep)
        fps = 4 if ep["cutoff_s"] - ep["start_s"] <= 30 else 2
        text, usage, lat = gemini(STRONG, QA_SYS, [video_part(ep, ep["start_s"], ep["cutoff_s"], fps, audio),
                                                   types.Part(text=question_text(ep))])
        return {"answer": text, "usage": usage, "latency_s": lat, "calls": 1, "video_fps": fps}

    def pro(ep):
        r = poll_proactive(ep, lambda t0, t1, f: gemini(STRONG, PRO_SYS, [
            video_part(ep, t0, t1, 4), types.Part(text=question_text(ep) + "\nWAIT or notification?")],
            max_tokens=48), period=2.0, lookback=6.0, fps=4)
        r["calls"] = len(r["polls"])
        return r
    return STRONG, qa, pro


def gamst_context(ep, t_end, state_rows, signal_rows):
    """Semantic State Fusion + Semantic State Chain -> MCP context, bounded by the cutoff."""
    sys.path.insert(0, os.environ.get("GAMST_SRC", "/srv/gamst"))
    from gamst.semantic_fusion import SemanticStateFusion
    from gamst.semantic_state import SemanticStateChain
    fusion, chain = SemanticStateFusion(max_signals=64, max_evidence=32), SemanticStateChain(
        max_updates=512, max_bytes=1024 * 1024, retention_ms=24 * 3600 * 1000)
    events = [("video", s["t1"], s) for s in state_rows.get("states", []) if s["t1"] <= t_end]
    events += [("signal", g["timestamp_ms"] / 1000, g) for g in signal_rows.get("signals", [])
               if g["timestamp_ms"] / 1000 <= t_end]
    for kind, t, item in sorted(events, key=lambda e: e[1]):
        ms = int(t * 1000)
        if kind == "video":
            fusion.observe_video_state({"summary": item["text"]}, timestamp_ms=ms,
                                       evidence_ids=[f"frame:{item['t0']:.1f}-{item['t1']:.1f}"],
                                       model_id="mit-han-lab/StreamingVLM",
                                       model_version="7ac1cef46d20432053a9814838760318cb26b348")
            chain.append("ep", timestamp_ms=ms, state={"video": item["text"]},
                         evidence_ids=[f"frame:{item['t0']:.1f}-{item['t1']:.1f}"], sources=["video"],
                         model_id="mit-han-lab/StreamingVLM", model_version="7ac1cef")
        else:
            fusion.observe_signal(item)
            chain.append("ep", timestamp_ms=ms, state={"signal": item["plugin"], "value": item["value"]},
                         events=[{"type": item["plugin"], "t": round(t, 3)}],
                         evidence_ids=item["evidence_ids"], sources=[item["modality"]],
                         model_id=item["plugin"], model_version="1")
    view = chain.get("ep", limit=256)
    compact = [{"t": round(u["timestamp_ms"] / 1000, 2), **u["state"]} for u in view["updates"]]
    return {"semantic_state_chain": compact,
            "fusion": fusion.snapshot(timestamp_ms=int(t_end * 1000)),
            "source": "gamst.semantic_fusion+semantic_state", "cutoff_s": t_end}


def keyframes(ep, t_end, signal_rows, k=6):
    peaks = sorted({round(g["value"].get("peak_s", g["value"].get("onset_s")), 1)
                    for g in signal_rows.get("signals", []) if g["timestamp_ms"] / 1000 <= t_end})
    picks = cap(peaks, k - 1) + [max(ep["start_s"], t_end - 0.25)]
    out = []
    for t in picks:
        fr = frames(ep, 4, t, t + 0.25)
        if fr:
            out.append(fr[0])
    return out


def arm_gamst(media=True):
    """media=False: raw frames are discarded; the strong model sees only the MCP state context."""
    from google.genai import types
    states = {json.loads(l)["id"]: json.loads(l) for l in SVLM_STATE.open()}
    signals = {json.loads(l)["id"]: json.loads(l) for l in SIGNALS.open()}

    def ask(ep, t_end, system, text, max_tokens):
        ctx = gamst_context(ep, t_end, states[ep["id"]], signals[ep["id"]])
        kf = keyframes(ep, t_end, signals[ep["id"]]) if media else []
        parts = [types.Part(text="MCP context (GAMST semantic state chain):\n" +
                            json.dumps(ctx, ensure_ascii=False))] + image_parts(kf) + [types.Part(text=text)]
        out = gemini(STRONG, system, parts, max_tokens=max_tokens)
        return out, len(kf), len(json.dumps(ctx))

    def qa(ep):
        (text, usage, lat), nkf, ctx_bytes = ask(ep, ep["cutoff_s"], QA_SYS, question_text(ep), 256)
        return {"answer": text, "usage": usage, "latency_s": lat, "calls": 1, "keyframes": nkf,
                "context_bytes": ctx_bytes, "streamingvlm_rtf": states[ep["id"]]["realtime_factor"]}

    def pro(ep):
        # frozen application rule: strong call only on a new modality signal or a StreamingVLM
        # state change, at most every 2 s; GAMST itself never triggers.
        sigs = sorted(g["timestamp_ms"] / 1000 for g in signals[ep["id"]]["signals"])
        st = states[ep["id"]]["states"]
        changes = [s["t1"] for k, s in enumerate(st) if k == 0 or s["text"].strip() != st[k - 1]["text"].strip()]
        triggers, last = [], -1e9
        for t in sorted(set(round(x, 2) for x in sigs + changes)):
            if ep["start_s"] < t <= ep["ref_sec"] + 2.0 and t - last >= 2.0:
                triggers.append(t)
                last = t
        polls = []
        for t in triggers:
            (text, usage, lat), nkf, ctx_bytes = ask(ep, t, PRO_SYS, question_text(ep) +
                                                     "\nWAIT or notification?", 48)
            polls.append({"t": t, "text": text, "usage": usage, "latency_s": round(lat, 3),
                          "keyframes": nkf, "context_bytes": ctx_bytes})
            if text and not text.upper().startswith("WAIT"):
                return {"answer": text, "speak_t": t, "polls": polls, "calls": len(polls)}
        return {"answer": "", "speak_t": None, "polls": polls, "calls": len(polls)}
    return STRONG, qa, pro


async def live_episode(ep):
    """One Gemini Live session per episode: 1 FPS JPEG + 16 kHz PCM paced in real time.

    Manual activity detection: each user turn is [activity_start, AV media, text, activity_end].
    Proactive: one turn per video second (WAIT or notification). QA: one turn spanning the
    whole window with the question at the cutoff.
    """
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project=PROJECT, location=os.environ.get("HF_LIVE_LOC", "us-central1"))
    proactive = ep["scoring"] == "proactive"
    modality = os.environ.get("HF_LIVE_MODALITY", "AUDIO")
    cfg = types.LiveConnectConfig(
        response_modalities=[modality],
        output_audio_transcription=types.AudioTranscriptionConfig() if modality == "AUDIO" else None,
        system_instruction=PRO_SYS if proactive else QA_SYS,
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)))
    fl = frames(ep, 1, width=640)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip_path(ep)), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    polls, answer, speak_t, usage = [], "", None, []
    async with client.aio.live.connect(model=LIVE, config=cfg) as s:
        async def collect():
            said = []
            async for msg in s.receive():
                sc = msg.server_content
                if msg.usage_metadata and msg.usage_metadata.total_token_count:
                    usage.append(msg.usage_metadata.total_token_count)
                if modality == "TEXT" and msg.text:
                    said.append(msg.text)
                if sc and sc.output_transcription and sc.output_transcription.text:
                    said.append(sc.output_transcription.text)
                if sc and sc.turn_complete:
                    break
            return "".join(said).strip()

        async def media(i):
            await s.send_realtime_input(video=types.Blob(data=base64.b64decode(fl[i][1]), mime_type="image/jpeg"))
            chunk = pcm[i * 32000:(i + 1) * 32000]
            if chunk:
                await s.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))

        t_start = time.time()
        if not proactive:
            await s.send_realtime_input(activity_start=types.ActivityStart())
        for i, (t, _) in enumerate(fl):
            if proactive:
                await s.send_realtime_input(activity_start=types.ActivityStart())
                await media(i)
                await s.send_realtime_input(text=question_text(ep) + "\nWAIT or notification?")
                await s.send_realtime_input(activity_end=types.ActivityEnd())
                # one activity span can yield an extra empty turn; read until a spoken reply (≤10 s)
                txt = await collect()
                while not txt:
                    try:
                        txt = await asyncio.wait_for(collect(), timeout=10)
                    except asyncio.TimeoutError:
                        break
                polls.append({"t": round(t + 1, 2), "text": txt})
                if txt and not txt.upper().startswith("WAIT"):
                    answer, speak_t = txt, round(t + 1, 2)
                    break
                if t + 1 > ep["ref_sec"] + 2:
                    break
            else:
                await media(i)
            await asyncio.sleep(max(0.0, (i + 1) - (time.time() - t_start)))
        if not proactive:
            await s.send_realtime_input(text=question_text(ep))
            await s.send_realtime_input(activity_end=types.ActivityEnd())
            answer = await collect()
    return {"answer": answer, "speak_t": speak_t, "polls": polls, "calls": max(1, len(polls)),
            "live_model": LIVE, "modality": modality, "usage_total_tokens": sum(usage)}


def cmd_arm(name):
    out = ROOT / f"arm_{name}.jsonl"
    done = done_ids(out)
    allowed = set(json.loads((ROOT / "admission.json").read_text())["admitted"])
    eps = [e for e in episodes() if e["id"] not in done and e["id"] in allowed]
    if name == "strong_videoonly":  # AV ablation gate for T3: same strong call, audio removed
        eps = [e for e in eps if e["family"] == "T3_av_sync"]
    if name == "gemini_live":
        async def main():
            sem = asyncio.Semaphore(int(os.environ.get("HF_LIVE_CONC", "4")))

            async def one(ep):
                async with sem:
                    t = time.time()
                    try:
                        r = await live_episode(ep)
                        err = None
                    except Exception as exc:
                        r, err = {"answer": ""}, f"{type(exc).__name__}: {exc}"[:300]
                    append(out, {"id": ep["id"], "arm": name, **r, "wall_s": time.time() - t, "error": err})
                    print(name, ep["id"], err, flush=True)
            await asyncio.gather(*(one(e) for e in eps))
        asyncio.run(main())
        return
    model, qa, pro = {"qwen_small": arm_local, "streamingvlm": arm_local,
                      "strong": lambda n: arm_strong(), "strong_videoonly": lambda n: arm_strong(audio=False),
                      "gamst": lambda n: arm_gamst(),
                      "gamst_nomedia": lambda n: arm_gamst(media=False)}[name](name)
    import concurrent.futures
    import threading
    lock = threading.Lock()

    def one(ep):
        t = time.time()
        try:
            r, err = (pro if ep["scoring"] == "proactive" else qa)(ep), None
        except Exception as exc:
            r, err = {"answer": ""}, f"{type(exc).__name__}: {exc}"[:300]
        with lock:
            append(out, {"id": ep["id"], "arm": name, "model": model, **r, "wall_s": time.time() - t, "error": err})
        print(name, ep["id"], err, flush=True)
    workers = int(os.environ.get("HF_CONC", "4")) if name in (
        "strong", "strong_videoonly", "gamst", "gamst_nomedia") else 2
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, eps))


# ---------------------------------------------------------------- admission + judge
_judged = {}


def cmd_plugin_episodes():
    """Admitted episodes for the StreamingVLM state runner and the modality plugins."""
    allowed = set(json.loads((ROOT / "admission.json").read_text())["admitted"])
    with (ROOT / "plugin_episodes.jsonl").open("w") as f:
        for ep in episodes():
            if ep["id"] in allowed:
                f.write(json.dumps({"id": ep["id"], "video": str(clip_path(ep)),
                                    "offset_s": ep["start_s"], "cutoff_s": ep["cutoff_s"]}) + "\n")


def judge_text(ep, pred):
    sys.path.insert(0, os.environ.get("SA_SRC", "/srv/StreamArena"))
    from streamarena.judge import JUDGE_PROMPT_TMPL, JUDGE_PROMPT_TMPL_E
    tmpl = JUDGE_PROMPT_TMPL_E if ep["scoring"] == "proactive" else JUDGE_PROMPT_TMPL
    key = (ep["id"], pred)
    if key not in _judged:
        raw = gemini(JUDGE, "You are an impartial judge.",
                     [tmpl.format(question=ep["question"], gt=ep["answer"], pred=pred)],
                     max_tokens=8, thinking="low")[0]
        _judged[key] = raw.strip().lower().startswith("correct")
    return _judged[key]


def score(ep, r):
    """StreamArena correctness; proactive uses the official [-0.5, +2.0] s window."""
    if not r or r.get("error") or not (r.get("answer") or "").strip():
        return False, "empty_or_error"
    if ep["scoring"] == "proactive":
        if r.get("speak_t") is None:
            return False, "missed"
        delta = r["speak_t"] - ep["ref_sec"]
        if delta < -0.5:
            return False, f"premature {delta:+.1f}s"
        if delta > 2.0:
            return False, f"late {delta:+.1f}s"
        return judge_text(ep, r["answer"]), "judged"
    answer, _ = split_answer(r["answer"])
    return (bool(answer) and judge_text(ep, answer)), "judged"


def extras(ep, r, correct):
    """Added GAMST-HF metrics: strict +-0.5 s alert timing; evidence-time hit (+-2 s) for HR."""
    out = {}
    if ep["scoring"] == "proactive":
        out["strict_correct"] = bool(correct and abs(r["speak_t"] - ep["ref_sec"]) <= 0.5)
    elif ep.get("evidence_ts_sec"):
        _, ev = split_answer(r.get("answer"))
        out["evidence_t"] = ev
        out["evidence_hit"] = any(abs(a - b) <= 2.0 for a in ev for b in ep["evidence_ts_sec"])
    return out


def cmd_judge_gates():
    gates = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "gate.jsonl").open()}
    errored = [g["id"] for g in gates.values() if g.get("error")]
    if len(errored) > 0.05 * len(episodes()):  # a crashed server must not silently shrink the set
        raise SystemExit(f"gate errors on {len(errored)} episodes; fix and rerun gate: {errored[:5]}")
    admitted_ids, rows = [], []
    for ep in episodes():
        g = gates.get(ep["id"])
        if g is None or g.get("error"):
            rows.append({"id": ep["id"], "family": ep["family"], "admitted": False,
                         "excluded": (g or {}).get("error", "no gate row")})
            continue
        if ep["scoring"] == "qa":
            c = {k: bool(split_answer(g[k])[0]) and judge_text(ep, split_answer(g[k])[0])
                 for k in ("1fps", "first_last", "shuffled")}
        else:
            c = {"1fps": score(ep, g["1fps"])[0]}
        ok = not c["1fps"] and not c.get("first_last", False)
        rows.append({"id": ep["id"], "family": ep["family"], "controls_correct": c, "admitted": ok})
        if ok:
            admitted_ids.append(ep["id"])
    (ROOT / "admission.json").write_text(json.dumps({"admitted": admitted_ids, "rows": rows,
                                                     "rule": "admit iff reference VLM fails 1FPS and first+last"},
                                                    indent=1))
    print("admitted", len(admitted_ids), "of", len(rows))


def cmd_judge_arms(names):
    eps = {e["id"]: e for e in episodes()}
    adm = set(json.loads((ROOT / "admission.json").read_text())["admitted"])
    summary = {}
    for name in names:
        path = ROOT / f"arm_{name}.jsonl"
        if not path.exists():
            continue
        rows = list({r["id"]: r for r in map(json.loads, path.open())}.values())  # newest row per id
        judged = []
        for r in rows:
            if r["id"] not in adm:
                continue
            ok, why = score(eps[r["id"]], r)
            judged.append({"id": r["id"], "family": eps[r["id"]]["family"], "correct": ok, "why": why,
                           "calls": r.get("calls"), "answer": r.get("answer"), "speak_t": r.get("speak_t"),
                           **extras(eps[r["id"]], r, ok)})
        with (ROOT / f"judged_{name}.jsonl").open("w") as f:
            for j in judged:
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
        summary[name] = {"n": len(judged), "correct": sum(j["correct"] for j in judged)}
        print(name, summary[name], flush=True)
    (ROOT / "summary_raw.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prep":
        cmd_prep()
    elif cmd == "gate":
        cmd_gate()
    elif cmd == "arm":
        cmd_arm(sys.argv[2])
    elif cmd == "plugin_episodes":
        cmd_plugin_episodes()
    elif cmd == "judge" and sys.argv[2] == "--gates":
        cmd_judge_gates()
    elif cmd == "judge":
        cmd_judge_arms(sys.argv[2].split(","))
