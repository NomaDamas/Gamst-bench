"""Select GAMST-HF candidate episodes from real StreamArena (YouTube) annotations.

No new labels are written: question, answer, ask/ref time and evidence times are
the human StreamArena annotations. This script only maps question types to the
agreed GAMST-HF task families, bounds each episode window, and draws a seeded
sample. Admission is decided later by the anti-shortcut gates.

usage: python build_candidates.py question.en.jsonl video_meta.en.jsonl OUT.jsonl N_PER_FAMILY SEED
"""
import hashlib
import json
import random
import re
import sys

AV = re.compile(r"\b(said|say|says|saying|speak|speaking|spoke|mention|mentioned|heard|hear|sound|"
                r"applause|commentator|host|announc|sing|song|music|voice|narrat|introduc)", re.I)
MAX_HR_SPAN = 240  # seconds of history a full-rate arm must watch

questions = [json.loads(line) for line in open(sys.argv[1])]
meta = {m["video_id"]: m for m in map(json.loads, open(sys.argv[2]))}
out, n, seed = sys.argv[3], int(sys.argv[4]), int(sys.argv[5])

families = {"T1_transient_alert": [], "T2_event_order_count": [], "T3_av_sync": [],
            "T4_last_seen": [], "T7_anytime_cutoff": []}
for q in questions:
    base = {"video_id": q["video_id"], "qid": q["qid"], "qtype": q["qtype"], "question": q["question"],
            "answer": q["answer"], "ask_sec": q["ask_sec"], "ref_sec": q["ref_sec"],
            "evidence_ts_sec": q["evidence_ts_sec"], "qdesc": q["qdesc"],
            "domain": meta[q["video_id"]]["L1"], "url": meta[q["video_id"]]["url"]}
    if q["qtype"] == "Pro" and q["horizon_layer"] == "L1":
        # proactive alert: silent in [ask, ref), speak within [ref-0.5, ref+2] (StreamArena timing)
        families["T1_transient_alert"].append({**base, "start_s": q["ask_sec"], "cutoff_s": q["ref_sec"] + 3,
                                               "scoring": "proactive"})
    elif q["qtype"] == "RTP":
        fam = "T3_av_sync" if AV.search(q["question"]) else "T7_anytime_cutoff"
        families[fam].append({**base, "start_s": max(0, q["ask_sec"] - 20), "cutoff_s": q["ask_sec"],
                              "scoring": "qa"})
    elif q["qtype"] == "HR" and q["evidence_ts_sec"]:
        first = min(q["evidence_ts_sec"])
        # evidence must precede the question (a few annotations point after ask_sec)
        if q["ask_sec"] - first > MAX_HR_SPAN or first <= 0 or max(q["evidence_ts_sec"]) >= q["ask_sec"]:
            continue
        fam = "T2_event_order_count" if len(q["evidence_ts_sec"]) > 1 else "T4_last_seen"
        families[fam].append({**base, "start_s": max(0, first - 10), "cutoff_s": q["ask_sec"],
                              "scoring": "qa"})
rows = []
for fam, items in families.items():
    items.sort(key=lambda r: (r["video_id"], r["qid"]))
    pick = random.Random(f"{seed}:{fam}").sample(items, min(n, len(items)))
    for r in sorted(pick, key=lambda r: (r["video_id"], r["qid"])):
        r["family"], r["id"] = fam, f"{r['video_id']}#{r['qid']}"
        rows.append(r)
    print(fam, "pool", len(items), "picked", len(pick))
with open(out, "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("rows", len(rows), "videos", len({r["video_id"] for r in rows}),
      "sha256", hashlib.sha256(open(out, "rb").read()).hexdigest())
