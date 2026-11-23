"""Run pinned upstream StreamingVLM natively and record its per-second video semantic state.

Video only. The upstream `streaming_inference()` loop (1 s chunks, 16 s visual
window, text sink/sliding window 512) is reused unchanged; this script only
iterates episodes and writes the timestamped outputs. Nothing after an
episode's query cutoff is decoded.

usage: python streamingvlm_state.py EPISODES.jsonl OUT.jsonl MODEL_DIR
EPISODES.jsonl rows: {"id", "video" (clip), "offset_s" (clip start, absolute), "cutoff_s"}
"""
import json
import pathlib
import sys
import time

from streaming_vlm.inference.inference import load_model_and_processor, streaming_inference

QUERY = (
    "Describe, second by second, what is happening in the video right now: "
    "objects, people, actions and any change of state."
)

episodes = [json.loads(line) for line in open(sys.argv[1])]
out = pathlib.Path(sys.argv[2])
done = set()
if out.exists():
    done = {json.loads(line)["id"] for line in out.open()}
model, processor = load_model_and_processor(sys.argv[3])
with out.open("a") as sink:
    for ep in episodes:
        if ep["id"] in done:
            continue
        start = float(ep["offset_s"])
        duration = max(1, int(float(ep["cutoff_s"]) - start))
        t0 = time.perf_counter()
        try:
            responses = streaming_inference(
                model=model, processor=processor, video_path=ep["video"],
                skip_first_chunk=0, duration=duration, query=QUERY,
                # upstream defaults (temperature 0.9, seed 42 set at import); near-greedy decoding
                # makes this commentary-trained checkpoint emit only " ..." every second
                previous_text="", text_sink=512, text_sliding_window=512, quiet=True,
            )
            error = None
        except Exception as exc:  # recorded, never silently dropped
            responses, error = [], f"{type(exc).__name__}: {exc}"
        wall = time.perf_counter() - t0
        sink.write(json.dumps({
            "id": ep["id"], "start_s": start, "cutoff_s": start + duration,
            "states": [{"t0": start + r["start_time"], "t1": start + r["end_time"], "text": r["response"]}
                       for r in responses],
            "wall_s": wall, "realtime_factor": wall / duration, "error": error,
        }, ensure_ascii=False) + "\n")
        sink.flush()
        print(ep["id"], len(responses), round(wall, 1), error, flush=True)
