"""MOT17 probability cloud: B vs C-local vs C-Gemini on the user rule
"tell me when someone is at <zone>" (zone rectangles from capability_lab, chosen on frame 1).

Ground truth (as capability_lab/zone_risk.py): human boxes, class 1, visibility >= 0.25; a person
occupies the zone when the box foot point (bottom centre) is inside it. Visits merge episodes with
gaps < 1.5 s.

Arms
- B (Qwen3.5-9B alone): every 1 s of video it sees the last 4 frames (1 fps) with the zone drawn
  and answers YES/NO "is someone in the zone now"; transitions to YES are its alerts. Memory
  questions are answered from the same sliding window.
- GAMST (shared by C arms): the crew outputs (all video models ran concurrently) are replayed into
  GAMST; RF-DETR person foot points feed GAMST RiskField (log-odds cloud with hysteresis). jev
  (Qwen3.8-27B-FP8) turns the user's sentence into a Watch via the MCP create_watch tool.
  Watch alarms are the only trigger.
- C-local / C-Gemini: on every Watch alarm the consumer gets the alarm (with per-evidence
  contributions and its time-window context) and decides NOTIFY / IGNORE; memory questions are
  answered from the MCP timeline + Watch alarm log.

usage: python eval_mot17.py SEQ_NAME  (writes /srv/par/eval/mot17/<seq>/arms.json)
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumers import ask_gemini, ask_local, jev_create_watch  # noqa: E402
from gamst_replay import Replay  # noqa: E402

DATA = Path("/srv/data/mot/train")
OUT = Path("/srv/par/eval/mot17")
ZONES = {"MOT17-09-FRCNN": [245.0, 683.0, 1060.0, 880.0], "MOT17-04-FRCNN": [854.0, 573.0, 1440.0, 854.0]}
PLACES = {"MOT17-09-FRCNN": "the shop entrance", "MOT17-04-FRCNN": "the marked road area"}
MERGE_GAP_S, MIN_EPISODE_S = 1.5, 0.5


def seqinfo(seq):
    ini = dict(line.strip().split("=", 1) for line in open(DATA / seq / "seqinfo.ini") if "=" in line)
    return float(ini["frameRate"]), int(ini["seqLength"]), int(ini["imWidth"]), int(ini["imHeight"])


def inside(zone, x, y):
    return zone[0] <= x <= zone[2] and zone[1] <= y <= zone[3]


def gt_occupancy(seq, zone, n):
    occ = np.zeros(n, dtype=bool)
    for line in open(DATA / seq / "gt" / "gt.txt"):
        f, _, x, y, w, h, flag, cls, vis = line.strip().split(",")[:9]
        if int(flag) == 1 and int(cls) == 1 and float(vis) >= 0.25 and inside(zone, float(x) + float(w) / 2, float(y) + float(h)):
            occ[int(f) - 1] = True
    return occ


def episodes(mask, fps):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if (j - i) / fps >= MIN_EPISODE_S:
                out.append([i / fps, j / fps])
            i = j
        else:
            i += 1
    return out


def visits(eps):
    merged = []
    for a, b in eps:
        if merged and a - merged[-1][1] < MERGE_GAP_S:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return merged


def interval_mask(intervals, n, fps):
    m = np.zeros(n, dtype=bool)
    for a, b in intervals:
        m[int(a * fps):int(math.ceil(b * fps))] = True
    return m


def score(pred_mask, alerts, gt_mask, gt_visits):
    tp = int((pred_mask & gt_mask).sum())
    hits, latencies, false = 0, [], 0
    for a, b in gt_visits:
        onset = [t for t in alerts if a - 1.0 <= t <= b]
        if onset:
            hits += 1
            latencies.append(round(onset[0] - a, 2))
    false = sum(1 for t in alerts if not any(a - 1.0 <= t <= b + 1.0 for a, b in gt_visits))
    return {"frame_precision": round(tp / max(1, pred_mask.sum()), 3), "frame_recall": round(tp / max(1, gt_mask.sum()), 3),
            "visits": len(gt_visits), "visits_alerted": hits, "false_alerts": false, "alert_latency_s": latencies}


def frame_jpeg(seq, index, zone, width=640):
    img = cv2.imread(str(DATA / seq / "img1" / f"{index + 1:06d}.jpg"))
    cv2.rectangle(img, (int(zone[0]), int(zone[1])), (int(zone[2]), int(zone[3])), (0, 0, 255), 6)
    scale = width / img.shape[1]
    img = cv2.resize(img, (width, int(img.shape[0] * scale)))
    return base64.b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()).decode()


# ---------------------------------------------------------------- B
def arm_b(seq, zone, fps, n, place):
    rule = f"Tell me when someone is at {place} (the red rectangle)."
    polls, state, alerts, calls, tokens = [], False, [], 0, 0
    for second in range(1, int(n / fps) + 1):
        frames = [(t, frame_jpeg(seq, min(n - 1, int(t * fps)), zone)) for t in range(max(0, second - 3), second + 1)]
        text, usage, _ = ask_local(
            "You watch a live camera. The user rule: " + rule +
            " Look at the newest frame. Reply YES if a person is standing or walking inside the red rectangle now, else NO.",
            "YES or NO?", frames, max_tokens=4)
        calls += 1
        tokens += (usage or {}).get("total_tokens", 0)
        yes = text.strip().upper().startswith("YES")
        polls.append([second, yes])
        if yes and not state:
            alerts.append(float(second))
        state = yes
    occupied = [[t - 1.0, float(t)] for t, yes in polls if yes]
    memory = []
    window = [(t, frame_jpeg(seq, min(n - 1, int(t * fps)), zone)) for t in range(max(0, int(n / fps) - 3), int(n / fps) + 1)]
    for q in memory_questions(place):
        text, usage, _ = ask_local("You watch a live camera. Answer from what you can see.", q, window, max_tokens=48)
        calls += 1
        tokens += (usage or {}).get("total_tokens", 0)
        memory.append({"q": q, "a": text})
    return {"occupied": occupied, "alerts": alerts, "memory": memory, "calls": calls, "tokens": tokens}


def memory_questions(place):
    return [f"How many separate times did someone come to {place} so far? Reply with a number.",
            f"At what video second did the most recent visit to {place} start? Reply with a number."]


# ---------------------------------------------------------------- GAMST + C
async def gamst_side(seq, zone, fps, n, w, h, place, run_dir):
    sys.path.insert(0, "/srv/gamst")
    from gamst.capabilities import SensorMetadata
    from gamst.plugins import InputFrame
    from gamst.providers.risk_field import RiskField
    replay = Replay(str(HERE / "stack.json"), str(run_dir))
    rect = [zone[0] / w, zone[1] / h, zone[2] / w, zone[3] / h]
    rule = {"id": "zone", "zones": [{"id": "zone", "rect": rect}],
            "evidence": [{"id": "person_in_zone", "kind": "presence", "zone": "zone", "weight": 1.0, "sigma": 60 / w}],
            "bias": 0.35, "tau_s": 1.5, "gain": 10.0, "on": 0.8, "off": 0.4}
    field = RiskField(rule)
    replay.human.register_capability(field.spec)
    tools = [t for t in (await replay.mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]
             if t["name"] == "create_watch"]
    caps = await replay.tool("list_capabilities", {"limit": 100})
    request = f"Tell me when someone is at {place}. Do not repeat the same alert within 3 seconds."
    from gamst.watch import validate_rule
    watch, jev_log = jev_create_watch(request, tools, caps, hint={"capability_id": field.spec.id,
                                                                    "fields": ["risk", "alarm"]},
                                      validate=lambda args: validate_rule(args["rule"]))
    created = await replay.tool("create_watch", watch) if watch else None
    alarms = []
    replay.human.watches.add_sink(alarms.append)
    det_rows = [r for r in replay.rows if r["worker"] == "rfdetr_large"]
    seq_no = 0
    for row in det_rows:
        media_s = (row["timestamp_ms"] - replay.epoch_ms) / 1000
        await replay.advance(media_s)
        points = [[o["location"]["bbox"]["x"] + o["location"]["bbox"]["width"] / 2,
                   o["location"]["bbox"]["y"] + o["location"]["bbox"]["height"]]
                  for o in row["value"]["objects"] if o["label"] == "person"][:64]
        sensor = SensorMetadata(source_id="media0", sensor_id="riskfield", sequence=seq_no)
        seq_no += 1
        value = field.process(InputFrame(data={"points": points}, modality="video",
                                         timestamp_ms=row["timestamp_ms"], sensor=sensor))
        await replay.human.push_observation(field.spec.id, value, sensor=sensor, timestamp_ms=row["timestamp_ms"])
    await replay.advance(n / fps + 1)
    # Risk alarm intervals from the field state (what GAMST holds), as media seconds.
    risk = await replay.pages(field.spec.id)
    on, intervals = None, []
    for r in risk:
        t = (r["timestamp_ms"] - replay.epoch_ms) / 1000
        if r["observation"]["value"]["alarm"] and on is None:
            on = t
        elif not r["observation"]["value"]["alarm"] and on is not None:
            intervals.append([on, t])
            on = None
    if on is not None:
        intervals.append([on, n / fps])
    timeline = await replay.timeline(max_chars=30000)
    alarm_log = [{"t": round((a["fired_ms"] - replay.epoch_ms) / 1000, 2), "score": a["score"],
                  "contributions": a["contributions"]} for a in alarms]
    return {"watch_request": request, "watch_args": watch, "watch_created": created, "jev": jev_log,
            "risk_intervals": intervals, "alarms": alarm_log, "timeline": timeline,
            "replay_skipped": dict(replay.skipped), "alarm_objects": alarms}


def arm_c(name, gamst, place):
    ask = ask_local if name == "C-local" else ask_gemini
    decided, calls, tokens = [], 0, 0
    for alarm in gamst["alarms"]:
        context = f"Watch alarm at t={alarm['t']}s (rule: someone at {place}). Evidence contributions: {json.dumps(alarm['contributions'])}"
        recent = "\n".join(line for line in gamst["timeline"].splitlines()
                           if line.startswith("t=") and alarm["t"] - 10 <= float(line[2:line.index("s")]) <= alarm["t"])
        text, usage, _ = ask("You are the application receiving GAMST MCP alarms for a user. Reply NOTIFY: <short message> "
                             "if the user should be told now, otherwise IGNORE.",
                             context + "\nMCP timeline (last 10 s):\n" + recent, [], max_tokens=40)
        calls += 1
        tokens += (usage or {}).get("total_tokens", 0)
        decided.append({"t": alarm["t"], "reply": text, "notify": text.strip().upper().startswith("NOTIFY")})
    memory = []
    for q in memory_questions(place):
        log = json.dumps(gamst["alarms"])
        text, usage, _ = ask("Answer the user's question from the GAMST MCP context only.",
                             f"Watch alarm log: {log}\nMCP timeline:\n{gamst['timeline'][-20000:]}\n\nQuestion: {q}", [], max_tokens=48)
        calls += 1
        tokens += (usage or {}).get("total_tokens", 0)
        memory.append({"q": q, "a": text})
    alerts = [d["t"] for d in decided if d["notify"]]
    return {"alerts": alerts, "decisions": decided, "memory": memory, "calls": calls, "tokens": tokens}


def main():
    seq = sys.argv[1]
    fps, n, w, h = seqinfo(seq)
    zone, place = ZONES[seq], PLACES[seq]
    out_dir = OUT / seq
    gt_mask = gt_occupancy(seq, zone, n)
    gt_visits = visits(episodes(gt_mask, fps))
    result = {"sequence": seq, "fps": fps, "frames": n, "zone_px": zone, "gt_visits": gt_visits,
              "gt_memory": {"visits": len(gt_visits), "last_visit_start_s": gt_visits[-1][0] if gt_visits else None}}
    gamst = asyncio.run(gamst_side(seq, zone, fps, n, w, h, place, out_dir / "crew"))
    result["gamst"] = {k: v for k, v in gamst.items() if k != "alarm_objects"}
    result["gamst"]["score"] = score(interval_mask(gamst["risk_intervals"], n, fps),
                                     [a["t"] for a in gamst["alarms"]], gt_mask, gt_visits)
    started = time.time()
    b = arm_b(seq, zone, fps, n, place)
    b["wall_s"] = round(time.time() - started, 1)
    b["score"] = score(interval_mask(b["occupied"], n, fps), b["alerts"], gt_mask, gt_visits)
    result["B"] = b
    for name in ("C-local", "C-Gemini"):
        started = time.time()
        c = arm_c(name, gamst, place)
        c["wall_s"] = round(time.time() - started, 1)
        accepted = [iv for iv in gamst["risk_intervals"] if any(iv[0] - 0.5 <= t <= iv[1] for t in c["alerts"])]
        c["score"] = score(interval_mask(accepted, n, fps), c["alerts"], gt_mask, gt_visits)
        result[name] = c
    (out_dir / "arms.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(json.dumps({k: result[k]["score"] for k in ("gamst", "B", "C-local", "C-Gemini")}, indent=1))


if __name__ == "__main__":
    main()
