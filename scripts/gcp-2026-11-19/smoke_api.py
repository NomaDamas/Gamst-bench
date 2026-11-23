"""Smoke-check the Vertex arms on one real QA and one proactive episode (no scoring)."""
import asyncio
import json
import sys

sys.path.insert(0, "/srv/bench/scripts/gcp-2026-11-19")
import hf_bench as hb  # noqa: E402

eps = hb.episodes()
qa = next(e for e in eps if e["scoring"] == "qa" and e["cutoff_s"] - e["start_s"] <= 30)
pro = next(e for e in eps if e["scoring"] == "proactive")
_, sqa, spro = hb.arm_strong()
r = sqa(qa)
print("strong qa", qa["id"], "gt:", qa["answer"], "->", json.dumps(r)[:400], flush=True)
judge = hb.judge_text(qa, r["answer"])
print("judge", judge, flush=True)
if "--live" in sys.argv:
    print("live qa", json.dumps(asyncio.run(hb.live_episode(qa)))[:500], flush=True)
    print("live pro", pro["id"], pro["ref_sec"], json.dumps(asyncio.run(hb.live_episode(pro)))[:800], flush=True)
