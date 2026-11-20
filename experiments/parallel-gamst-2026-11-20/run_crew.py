"""Run a set of GAMST model workers (and optional model servers) at once on one media file.

    python run_crew.py --stack stack.json --media clip.mp4 --out runs/<id> [--only a,b] [--speed 1]

``stack.json`` lists every worker/server with its Python environment, GAMST
profile, config and GPU memory budget (see ``stack.json`` in this folder).
All selected models run concurrently; the media is published once at
wall-clock pace. Output: results.jsonl, monitor.jsonl, summary.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    parser.add_argument("--media", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--max-side", type=int, default=1280)
    parser.add_argument("--keep-servers", action="store_true",
                        help="servers in the stack are already running; do not start them")
    args = parser.parse_args()

    stack = json.loads(Path(args.stack).read_text())
    sys.path.insert(0, stack["crew_root"])
    from gamstcrew.media_bus import AudioRing, FrameRing
    from gamstcrew.media_source import MediaSource, probe
    from gamstcrew.parallel import ParallelCrew, ServerSpec, WorkerSpec

    only = {name for name in args.only.split(",") if name}
    def resolve(config):
        # "@/abs/path.json" values are replaced by that file's JSON (e.g. per-file hash manifests).
        return {k: json.loads(Path(v[1:]).read_text()) if isinstance(v, str) and v.startswith("@/") else v
                for k, v in config.items()}

    workers = [WorkerSpec(**{**w, "config": resolve(w["config"])}) for w in stack["workers"]
               if not only or w["name"] in only]
    # Servers always hold their VRAM reservation; --keep-servers only skips (re)starting them.
    servers = [ServerSpec(**s) for s in stack.get("servers", [])]

    info = probe(args.media, args.max_side)
    tag = uuid.uuid4().hex[:8]
    need_video = any(w.input["kind"] == "video" for w in workers)
    need_audio = any(w.input["kind"] == "audio" for w in workers)
    if need_audio and not info["has_audio"]:
        raise SystemExit("selected audio workers but media has no audio track")
    frame_ring = FrameRing.create(f"gamst_v_{tag}", info["height"], info["width"], slots=96) if need_video else None
    audio_ring = AudioRing.create(f"gamst_a_{tag}") if need_audio else None

    crew = ParallelCrew(args.out, workers=workers, servers=servers, crew_root=stack["crew_root"],
                        gamst_root=stack["gamst_root"], strict_budget=stack.get("strict_budget", True))
    (Path(args.out) / "run.json").write_text(json.dumps({
        "media": args.media, "probe": info, "speed": args.speed, "workers": [w.name for w in workers],
        "servers": [s.name for s in servers], "budgets": crew.reserve_all()}, indent=1))
    source = MediaSource(args.media, frame_ring, audio_ring, info, speed=args.speed)
    try:
        if not args.keep_servers:
            crew.start_servers()
        # Workers stamp outputs with epoch + pts; the epoch is fixed before any frame exists.
        media_epoch_ms = int(time.time() * 1000)
        crew.start_workers(frame_ring.segment.name if frame_ring else None,
                           audio_ring.segment.name if audio_ring else None, media_epoch_ms, f"run-{tag}")
        crew.wait_ready()
        crew.start_monitor(source.clock)
        started = time.time()
        source.run()
        crew.finish_media()
        crew.drain()
        wall = time.time() - started
        summary = crew.summary(info["duration_s"] / 1.0, wall)
        summary["source"] = {"published_frames": source.published_frames, "late_frames": source.late_frames,
                             "speed": args.speed}
        (Path(args.out) / "summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps({name: {k: v for k, v in m.items() if k in (
            "processed", "dropped", "drop_rate", "busy_rtf", "compute_ms_mean", "latency_ms_p50",
            "latency_ms_p95", "gpu_peak_mib", "budget_mib", "errors", "exit_code")}
            for name, m in summary["models"].items()}, indent=1))
    finally:
        crew.stop()
        for ring in (frame_ring, audio_ring):
            if ring is not None:
                ring.close()


if __name__ == "__main__":
    main()
