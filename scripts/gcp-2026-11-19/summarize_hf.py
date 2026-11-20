"""Summarize the GAMST-HF run: admission gates, per-arm accuracy by family, calls, tokens, latency.

usage: python summarize_hf.py HF_ROOT OUT.json
Every number is recomputed from the raw JSONL artifacts in HF_ROOT.
"""
import collections
import hashlib
import json
import pathlib
import statistics
import sys

root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ARMS = ["qwen_small", "streamingvlm", "gemini_live", "strong", "strong_videoonly", "gamst", "gamst_nomedia"]
adm = json.loads((root / "admission.json").read_text())


def tokens(row):
    total = 0
    for u in [row.get("usage")] + [p.get("usage") for p in row.get("polls", [])]:
        if isinstance(u, dict):
            total += (u.get("prompt_token_count") or u.get("prompt_tokens") or 0)
    return total or row.get("usage_total_tokens") or 0


gate = collections.defaultdict(lambda: {"candidates": 0, "admitted": 0, "1fps_correct": 0,
                                        "first_last_correct": 0, "shuffled_correct": 0})
for r in adm["rows"]:
    g = gate[r["family"]]
    g["candidates"] += 1
    g["admitted"] += int(r["admitted"])
    for k, v in (r.get("controls_correct") or {}).items():
        g[f"{k}_correct"] += int(v)

# AV ablation gate (T3): AV-verified iff strong(video+audio) correct and strong(video only) wrong
av_verified = None
if (root / "judged_strong.jsonl").exists() and (root / "judged_strong_videoonly.jsonl").exists():
    s_av = {j["id"]: j["correct"] for j in map(json.loads, (root / "judged_strong.jsonl").open())}
    s_v = {j["id"]: j["correct"] for j in map(json.loads, (root / "judged_strong_videoonly.jsonl").open())}
    av_verified = sorted(i for i in s_v if s_av.get(i) and not s_v[i])

arms = {}
for arm in ARMS:
    jp, rp = root / f"judged_{arm}.jsonl", root / f"arm_{arm}.jsonl"
    if not jp.exists():
        continue
    judged = [json.loads(l) for l in jp.open()]
    raw = {json.loads(l)["id"]: json.loads(l) for l in rp.open()}
    fam = collections.defaultdict(lambda: [0, 0])
    for j in judged:
        fam[j["family"]][0] += int(j["correct"])
        fam[j["family"]][1] += 1
    lat = [p.get("latency_s") for r in raw.values() for p in ([r] + r.get("polls", [])) if p.get("latency_s")]
    arms[arm] = {
        "n": len(judged), "correct": sum(j["correct"] for j in judged),
        "accuracy": round(sum(j["correct"] for j in judged) / max(1, len(judged)), 4),
        "by_family": {f: {"correct": c, "n": n} for f, (c, n) in sorted(fam.items())},
        "errors": sum(1 for r in raw.values() if r.get("error")),
        "model_calls": sum(r.get("calls") or 0 for r in raw.values() if r["id"] in adm["admitted"]),
        "prompt_tokens": sum(tokens(r) for r in raw.values() if r["id"] in adm["admitted"]),
        "p50_call_latency_s": round(statistics.median(lat), 2) if lat else None,
        "fail_kinds": dict(collections.Counter(j["why"].split()[0] for j in judged if not j["correct"])),
        "alert_strict_0p5s": {"correct": sum(bool(j.get("strict_correct")) for j in judged if "strict_correct" in j),
                              "n": sum(1 for j in judged if "strict_correct" in j)},
        "evidence_time_hit_2s": {"hit": sum(bool(j.get("evidence_hit")) for j in judged if "evidence_hit" in j),
                                 "n": sum(1 for j in judged if "evidence_hit" in j)},
        "av_verified_T3": None if av_verified is None else {
            "correct": sum(j["correct"] for j in judged if j["id"] in av_verified), "n": len(av_verified)},
    }
state = root / "streamingvlm_state.jsonl"
svlm = [json.loads(l) for l in state.open()] if state.exists() else []
summary = {
    "dataset": "StreamArena en (real YouTube, human labels), seeded candidates; admission by anti-shortcut gates",
    "candidates_sha256": hashlib.sha256((root / "candidates.jsonl").read_bytes()).hexdigest(),
    "admission_rule": adm["rule"], "admitted": len(adm["admitted"]), "candidates": len(adm["rows"]),
    "gates_by_family": dict(gate), "av_verified_T3_ids": av_verified, "arms": arms,
    "streamingvlm_native": {"episodes": len(svlm),
                            "median_realtime_factor": round(statistics.median(
                                [s["realtime_factor"] for s in svlm]), 3) if svlm else None,
                            "errors": sum(1 for s in svlm if s.get("error"))},
}
out.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
print(json.dumps(summary, indent=1, ensure_ascii=False))
