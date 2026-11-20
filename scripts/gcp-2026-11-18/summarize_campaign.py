"""Summarize the 2026-11-18 GCP dev-subset campaign from raw run artifacts.

Every number comes from files written by the native runners, the vLLM-facing
dialog dumps (A arms) or the GAMST extension sidecars (C/D arms).
"""
import glob
import json
import pathlib
import sys

RUNS = pathlib.Path("/srv/gamst-runs")


def jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def sidecar_stats(path):
    rows = jsonl(path)
    calls = [r for r in rows if r["event"] == "vlm_call"]
    latency = [r["vlm_call_completed_unix_ms"] - r["vlm_call_started_unix_ms"] for r in calls]
    prompt = [int((r.get("usage") or {}).get("prompt_tokens") or 0) for r in calls]
    completion = [int((r.get("usage") or {}).get("completion_tokens") or 0) for r in calls]
    return {
        "observed_inputs": sum(1 for r in rows if r["event"] in ("selection", "audio")),
        "video_frames_observed": sum(1 for r in rows if r["event"] == "selection"),
        "backbone_calls": len(calls),
        "images_sent": len(calls),
        "prompt_tokens": sum(prompt),
        "completion_tokens": sum(completion),
        "call_latency_ms_sum": sum(latency),
        "call_latency_ms_p50": pct(latency, 0.5),
        "call_latency_ms_p95": pct(latency, 0.95),
        "errors": sum(1 for r in rows if r["event"] in ("vlm_error", "backend_error", "agent_error")),
        "input_drops": sum(1 for r in rows if r["event"] == "input_drop"),
        "coalesced_selections": sum(1 for r in rows if r["event"] == "selection_coalesced"),
        "native_emits": sum(1 for r in rows if r["event"] == "native_emit"),
    }


def dump_stats(root):
    metas = sorted(glob.glob(str(root / "dialog_dumps" / "*" / "*" / "*" / "meta.json")))
    status, elapsed, images = {}, [], 0
    for meta_path in metas:
        meta = json.loads(pathlib.Path(meta_path).read_text())
        code = str(meta.get("status_code"))
        status[code] = status.get(code, 0) + 1
        elapsed.append(float(meta.get("elapsed_ms") or 0))
        images += len(glob.glob(str(pathlib.Path(meta_path).parent / "image_*.jpg")))
    return {
        "backbone_calls": len(metas),
        "http_status": status,
        "images_sent": images,
        "call_latency_ms_sum": sum(elapsed),
        "call_latency_ms_p50": pct(elapsed, 0.5),
        "call_latency_ms_p95": pct(elapsed, 0.95),
    }


def fastbench(root):
    out = {"subset": json.loads((root / "subset-manifest.json").read_text())}
    out["subset"].pop("record_indices", None)
    out["subset"].pop("uuids", None)
    for arm in ["A-baseline", "C-gamst", "D-periodic", "A-proactive"]:
        arm_dir = root / arm
        if not (arm_dir / "status.json").exists():
            out[arm] = {"status": "not_run"}
            continue
        run_root = next(arm_dir.glob("qwen3_vl_*"), None)
        summary_path = run_root / "scoring" / "result_summary.json" if run_root else None
        entry = {"status": json.loads((arm_dir / "status.json").read_text())}
        entry["score"] = json.loads(summary_path.read_text()) if summary_path and summary_path.exists() else None
        if arm.startswith("A-"):
            entry["cost"] = dump_stats(run_root)
        else:
            entry["cost"] = sidecar_stats(arm_dir / "gamst-calls.jsonl")
        out[arm] = entry
    return out


def omnipro(root):
    out = {}
    for arm_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        metrics = arm_dir / "pred" / "metrics.json"
        entry = {"status": json.loads((arm_dir / "status.json").read_text()) if (arm_dir / "status.json").exists() else None,
                 "metrics": json.loads(metrics.read_text()) if metrics.exists() else None}
        if (arm_dir / "gamst-calls.jsonl").exists():
            entry["cost"] = sidecar_stats(arm_dir / "gamst-calls.jsonl")
        out[arm_dir.name] = entry
    return out


def streamarena(root):
    out = {}
    for arm_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        records = jsonl(arm_dir / "records.jsonl")
        judged = jsonl(arm_dir / "records.judged.jsonl")
        entry = {"status": json.loads((arm_dir / "status.json").read_text()) if (arm_dir / "status.json").exists() else None,
                 "records": len(records),
                 "cost": sidecar_stats(arm_dir / "gamst-calls.jsonl")}
        if judged:
            entry["judged"] = len(judged)
        out[arm_dir.name] = entry
    return out


if __name__ == "__main__":
    report = {
        "fastbench_dev50": fastbench(RUNS / "fastbench-r5" / "dev50"),
        "omnipro_dev45": omnipro(RUNS / "omnipro-r5" / "dev45") if (RUNS / "omnipro-r5" / "dev45").exists() else None,
        "streamarena_dev1": streamarena(RUNS / "streamarena-r7") if (RUNS / "streamarena-r7").exists() else None,
    }
    pathlib.Path(sys.argv[1]).write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1)[:6000])
