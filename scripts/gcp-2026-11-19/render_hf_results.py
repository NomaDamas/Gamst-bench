"""Render summary.json of the GAMST-HF run as the markdown result table (numbers only, no claims).

usage: python render_hf_results.py summary.json > table.md
"""
import json
import sys

s = json.load(open(sys.argv[1]))
FAM = ["T1_transient_alert", "T2_event_order_count", "T3_av_sync", "T4_last_seen", "T7_anytime_cutoff"]
ARMS = ["qwen_small", "streamingvlm", "gemini_live", "strong", "gamst", "gamst_nomedia", "strong_videoonly"]
print(f"Admitted {s['admitted']} of {s['candidates']} candidates ({s['admission_rule']}).\n")
print("| Arm | Correct | " + " | ".join(f.split("_", 1)[0] for f in FAM) +
      " | T1 strict ±0.5 s | Evidence ±2 s | Model calls | Prompt tokens | p50 call s |")
print("|---|---:|" + "---:|" * len(FAM) + "---:|---:|---:|---:|---:|")
for a in ARMS:
    v = s["arms"].get(a)
    if not v:
        continue
    fam = [f"{v['by_family'][f]['correct']}/{v['by_family'][f]['n']}" if f in v["by_family"] else "–" for f in FAM]
    st, ev = v["alert_strict_0p5s"], v["evidence_time_hit_2s"]
    print(f"| {a} | {v['correct']}/{v['n']} | " + " | ".join(fam) +
          f" | {st['correct']}/{st['n']} | {ev['hit']}/{ev['n']} | {v['model_calls']} | {v['prompt_tokens']:,} |"
          f" {v['p50_call_latency_s']} |")
print("\nFailure kinds:\n")
for a in ARMS:
    if a in s["arms"]:
        print(f"- {a}: {s['arms'][a]['fail_kinds']}")
av = s.get("av_verified_T3_ids")
if av is not None:
    print(f"\nAV-verified T3 items (strong right with audio, wrong without): {len(av)}")
    for a in ARMS:
        if a in s["arms"] and s["arms"][a].get("av_verified_T3"):
            x = s["arms"][a]["av_verified_T3"]
            print(f"- {a}: {x['correct']}/{x['n']}")
n = s["streamingvlm_native"]
print(f"\nStreamingVLM native state: {n['episodes']} episodes, median realtime factor {n['median_realtime_factor']},"
      f" errors {n['errors']}.")
