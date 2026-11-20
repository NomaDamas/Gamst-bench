"""Replay one ParallelCrew run into a GAMST runtime and read it back through MCP tools.

The crew wrote every model output with its capture timestamp (results.jsonl).
Replaying them into ``gamst.engine.Gamst`` in timestamp order reproduces the
state a live GAMST runtime had at any query time: the consumer only sees
records with ``timestamp_ms <= cutoff`` and only through MCP tool calls
(``get_observation_page``, ``get_transcripts``, Watch tools).

``timeline()`` is consumer-side formatting of those MCP tool results into a
bounded per-second text table, identical for every arm that reads GAMST.
"""
from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_results(run_dir: Path):
    rows = []
    for line in open(run_dir / "results.jsonl"):
        row = json.loads(line)
        if row.get("type") == "result" and row.get("timestamp_ms") is not None:
            rows.append(row)
    rows.sort(key=lambda r: (r["timestamp_ms"], r["worker"], r["seq"]))
    return rows


class Replay:
    def __init__(self, stack_path: str, run_dir: str, gamst_root: str = "/srv/gamst"):
        sys.path.insert(0, gamst_root)
        from gamst.capabilities import SensorMetadata
        from gamst.engine import Gamst
        from gamst.mcp import MCPServer
        from gamst.provider_profiles import capability
        self.SensorMetadata = SensorMetadata
        self.run_dir = Path(run_dir)
        stack = json.loads(Path(stack_path).read_text())
        run = json.loads((self.run_dir / "run.json").read_text())
        self.workers = {w["name"]: w for w in stack["workers"] if w["name"] in run["workers"]}
        self.specs = {}
        for name, w in self.workers.items():
            config = {k: json.loads(Path(v[1:]).read_text()) if isinstance(v, str) and v.startswith("@/") else v
                      for k, v in w["config"].items()}
            self.specs[name] = capability(w["profile"], config)
        self.human = Gamst(consent=True, store=":memory:", retention_hours=24 * 60, max_records=2_000_000,
                           max_payload_bytes=1 << 31, sensor_inference_interval_ms=5000)
        for spec in self.specs.values():
            self.human.register_capability(spec)
        self.mcp = MCPServer(self.human)
        self.rows = load_results(self.run_dir)
        self.epoch_ms = min((r["timestamp_ms"] - r["pts_ms"] for r in self.rows), default=0)
        self.cursor = 0
        self.sequence = defaultdict(int)
        self.skipped = defaultdict(int)

    async def advance(self, until_media_s: float) -> int:
        """Ingest every result captured at or before media time ``until_media_s``."""
        limit = self.epoch_ms + int(until_media_s * 1000)
        pushed = 0
        while self.cursor < len(self.rows) and self.rows[self.cursor]["timestamp_ms"] <= limit:
            row = self.rows[self.cursor]
            self.cursor += 1
            spec = self.specs.get(row["worker"])
            if spec is None:
                continue
            sensor = self.SensorMetadata(source_id="media0", sensor_id=row["worker"].replace("_", "-"),
                                         sequence=self.sequence[row["worker"]])
            self.sequence[row["worker"]] += 1
            try:
                await self.human.push_observation(spec.id, row["value"], sensor=sensor,
                                                  timestamp_ms=row["timestamp_ms"])
                pushed += 1
            except ValueError:
                self.skipped[row["worker"]] += 1
        return pushed

    async def tool(self, name: str, args: dict | None = None):
        return await self.mcp.call_tool(name, args or {})

    async def pages(self, capability_id: str, max_items: int = 5000):
        """All retained observations of one capability, oldest first, via get_observation_page."""
        items, cursor = [], None
        while len(items) < max_items:
            args = {"capability_id": capability_id, "limit": 100, "max_bytes": 262144}
            if cursor:
                args["cursor"] = cursor
            page = await self.tool("get_observation_page", args)
            items.extend(page.get("items", []))
            cursor = page.get("next_cursor")
            if not cursor or not page.get("items"):
                break
        return items

    def media_s(self, record) -> float:
        return round((record["timestamp_ms"] - self.epoch_ms) / 1000, 2)

    async def timeline(self, *, bin_s: float = 1.0, max_chars: int = 60000) -> str:
        """Per-second multimodal table from MCP reads, newest rows kept when over budget."""
        bins: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        peaks: dict[int, dict[str, int]] = defaultdict(dict)

        def put(t, key, text):
            if text and text not in bins[int(t // bin_s)][key]:
                bins[int(t // bin_s)][key].append(text)

        def peak(t, key, n):
            slot = peaks[int(t // bin_s)]
            slot[key] = max(slot.get(key, 0), n)

        for name, spec in self.specs.items():
            for record in await self.pages(spec.id):
                value, t = record.get("observation", {}).get("value", {}), self.media_s(record)
                if not isinstance(value, dict):
                    continue
                if "objects" in value:
                    labels = defaultdict(int)
                    for o in value["objects"]:
                        labels[o.get("label", "?")] += 1
                    put(t, "objects", ", ".join(f"{k}x{v}" for k, v in sorted(labels.items())))
                elif "poses" in value:
                    peak(t, "people_pose_max", len(value["poses"]))
                elif "hands" in value:
                    peak(t, "hands_max", len(value["hands"]))
                elif "faces" in value:
                    peak(t, "faces_max", len(value["faces"]))
                elif "summary" in value and "state" in value:
                    put(t, "scene", str(value["summary"])[:300])
                    for e in value.get("events", [])[:3]:
                        put(t, "scene_event", json.dumps(e, ensure_ascii=False)[:160])
                elif name.startswith("ced") and value.get("events"):
                    put(t, "sound", ", ".join(f"{e['label']}({e['score']:.2f})" for e in value["events"][:4]))
                elif "pulse_bpm" in value:
                    put(t, "pulse_bpm", str(value["pulse_bpm"]))
                elif "decisions" in value:
                    if value.get("state", {}).get("active"):
                        put(t, "voice", "speech")
                elif "risk" in value and "alarm" in value:
                    put(t, "zone_risk", f"{value['risk']:.2f}{' ALARM' if value['alarm'] else ''}")
                    for e in value.get("events", []):
                        put(t, "zone_event", e.get("event"))
                elif "diarization" in value:
                    for chunk in value["diarization"].get("chunks", []):
                        for slot in chunk.get("activity", []):
                            for start, _end in slot.get("intervals_ms", []):
                                put((start - self.epoch_ms) / 1000, "speaker_slots", f"S{slot['slot']}")
                elif "grid" in value:
                    summary = value.get("summary", {})
                    if isinstance(summary, dict) and summary:
                        put(t, "depth", json.dumps({k: summary[k] for k in list(summary)[:3]})[:120])
        transcripts = await self.tool("get_transcripts", {"window": "24h", "limit": 100, "max_bytes": 262144})
        for item in transcripts.get("items", []):
            u = item.get("latest", item)
            start = u.get("start_ms")
            if start is not None and u.get("text"):
                put((start) / 1000, "speech", f"\"{u['text']}\" ({u.get('status')})")
        for b, slot in peaks.items():
            for key, n in slot.items():
                if n:
                    bins[b][key].append(str(n))
        lines = []
        for b in sorted(bins):
            cells = [f"{k}: {'; '.join(v)}" for k, v in bins[b].items()]
            if cells:
                lines.append(f"t={b * bin_s:.0f}s | " + " | ".join(cells))
        text = "\n".join(lines)
        while len(text) > max_chars and lines:
            lines.pop(0)
            text = "\n".join(lines)
        return text


async def _demo(stack, run_dir, until):
    replay = Replay(stack, run_dir)
    pushed = await replay.advance(until)
    print("pushed", pushed, "skipped", dict(replay.skipped))
    print((await replay.timeline())[-4000:])


if __name__ == "__main__":
    asyncio.run(_demo(sys.argv[1], sys.argv[2], float(sys.argv[3])))
