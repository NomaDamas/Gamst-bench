"""Aggregate resumable StreamArena arm rows after Gemini-3.8-Flash judging.

Uses newest successful row per id, never Gemini 3.1 Pro. The judge files are produced on the VM;
copy them locally or run this script there with HF_ROOT set.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

ROOT = Path(os.environ.get("HF_ROOT", "/srv/hf"))
sys.path.insert(0, "/srv/hf")
import hf_bench_parallel as h


def newest(path):
    rows = {}
    if not path.exists(): return rows
    for line in path.open():
        if line.strip():
            r=json.loads(line)
            if not r.get("error"): rows[r["id"]]=r
    return rows


def main():
    admission=set(json.load((ROOT/"admission.json").open())["admitted"])
    episodes={e["id"]:e for e in h.episodes() if e["id"] in admission}
    result={}
    for name,path in (("B",ROOT/"judged_parallel_b.jsonl"),
                      ("C-local",ROOT/"arm_parallel_C_local.jsonl"),
                      ("C-Gemini",ROOT/"arm_parallel_C_Gemini.jsonl")):
        rows=newest(path)
        judged=[]
        for ident,r in rows.items():
            e=episodes.get(ident)
            if not e: continue
            ok,why=h.score(e,r) if path.name.startswith("judged") else (bool(r.get("answer")), "unjudged")
            judged.append({"id":ident,"correct":ok,"why":why,"family":e["family"],"calls":r.get("calls")})
        result[name]={"n":len(judged),"correct":sum(x["correct"] for x in judged),"rows":judged}
    (ROOT/"parallel_streamarena_summary.json").write_text(json.dumps(result,indent=1))
    print({k:{"n":v["n"],"correct":v["correct"]} for k,v in result.items()})

if __name__ == "__main__": main()
