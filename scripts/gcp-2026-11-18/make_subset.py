"""Freeze a seeded FastBench record subset and matching native configs (revision 4)."""
import hashlib
import json
import pathlib
import random
import sys

n, out, seed = int(sys.argv[1]), pathlib.Path(sys.argv[2]), int(sys.argv[3])
annotations = pathlib.Path("/srv/data/fastbench/proactive_perception_annotations.json")
records = json.loads(annotations.read_text())
indices = sorted(random.Random(seed).sample(range(len(records)), n))
subset = [records[i] for i in indices]
out.mkdir(parents=True, exist_ok=True)
(out / "subset.json").write_text(json.dumps(subset, ensure_ascii=False, indent=1))
for name in ["baseline", "proactive"]:
    text = pathlib.Path(f"/srv/gamst-runs/fastbench-measured/configs/{name}.yaml").read_text()
    text = text.replace(str(annotations), str(out / "subset.json"))
    (out / f"{name}.yaml").write_text(text)
uuids = [r.get("uuid") for r in subset]
meta = {
    "selection": f"random.Random({seed}).sample(range({len(records)}), {n}), sorted, native order",
    "records": n,
    "qa_pairs": sum(len(r.get("sqa") or r.get("verified_responses") or [1]) for r in subset),
    "record_indices": indices,
    "uuids": uuids,
    "uuids_sha256": hashlib.sha256("\n".join(map(str, uuids)).encode()).hexdigest(),
    "annotations_sha256": hashlib.sha256(annotations.read_bytes()).hexdigest(),
}
(out / "subset-manifest.json").write_text(json.dumps(meta, indent=2) + "\n")
print(json.dumps({k: v for k, v in meta.items() if k not in ("record_indices", "uuids")}))
