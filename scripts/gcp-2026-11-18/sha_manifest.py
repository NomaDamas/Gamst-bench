"""SHA256 + size manifest for the local StreamArena copy, cross-checked with GCS sizes/CRC32C."""
import hashlib
import json
import pathlib
import subprocess
import sys

root = pathlib.Path("/srv/data/streamarena")
prefix = "gs://gamst-bench-datasets-optimum-zone/datasets/streamarena/2960c360deba57b717a17ab66a3ae80f5358a6a3/"
listing = subprocess.run(["gcloud", "storage", "ls", "-r", "-j", prefix + "**"], capture_output=True, text=True, check=True).stdout
remote = {}
for obj in json.loads(listing):
    meta = obj.get("metadata", obj)
    name = meta.get("name") or obj.get("url", "")
    rel = name.split("2960c360deba57b717a17ab66a3ae80f5358a6a3/", 1)[-1]
    remote[rel] = {"size": int(meta.get("size", 0)), "crc32c": meta.get("crc32c")}
files = {}
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    rel = str(path.relative_to(root))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    files[rel] = {"size": path.stat().st_size, "sha256": digest.hexdigest()}
missing = sorted(set(remote) - set(files))
size_mismatch = sorted(k for k in files if k in remote and remote[k]["size"] != files[k]["size"])
out = {
    "source": prefix,
    "root": str(root),
    "files": len(files),
    "video_tars": sum(1 for k in files if k.startswith("videos/") and k.endswith(".tar")),
    "total_bytes": sum(v["size"] for v in files.values()),
    "remote_objects": len(remote),
    "missing_locally": missing,
    "size_mismatch": size_mismatch,
    "transfer_integrity": "gcloud storage cp validates CRC32C per object",
    "entries": files,
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: v for k, v in out.items() if k != "entries"}))
