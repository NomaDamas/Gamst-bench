import asyncio
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from gamst_bench.contracts import digest, verify_packet_checksum
from gamst_bench.collect import run_task
from gamst_bench.adapters.gamstcrew_runtime import Adapter


ROOT = Path(__file__).resolve().parents[1]


def _runtime_root(env_name: str, candidates: tuple[Path, ...]) -> Path:
    """Resolve an integration checkout without assuming a monorepo layout."""
    configured = os.environ.get(env_name)
    if configured:
        return Path(configured).expanduser().resolve()
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    # Keep the historical path as the diagnostic fallback when dependencies
    # are absent; the adapter then reports the precise missing-root failure.
    return candidates[0].resolve()


GAMST_ROOT = _runtime_root("GAMST_ROOT", (ROOT.parent / "catch-your-mind", ROOT.parent.parent))
CREW_ROOT = _runtime_root("GAMST_CREW_ROOT", (GAMST_ROOT / ".local-run" / "GamstCrew", ROOT.parent / "GamstCrew"))
ADAPTER = ROOT / "gamst_bench" / "adapters" / "gamstcrew_runtime.py"


CONFIG = {
    "id": "runtime-contract",
    "runtime": {
        "name": "geometry",
        "profile": "geometry.ground_plane",
        "python": sys.executable,
        "gamst_root": str(GAMST_ROOT),
        "crew_root": str(CREW_ROOT),
        "provider_config": {
            "id": "court-cal",
            "reference_id": "view-1",
            "source_id": "cam",
            "sensor_id": "points",
            "input_frame": "camera.image",
            "output_frame": "court.xy",
            "image_size": [640, 480],
            "valid_roi": [0.1, 0.1, 0.9, 0.9],
            "image_to_plane": [[10, 0, 0], [0, 20, 0], [0.5, 0, 1]],
        },
    },
    "subject_id": "local-user",
}


def messages(configuration=CONFIG):
    return [
        {"type": "start", "schema_version": 2,
         "configuration": configuration,
         "consumer_model": "runtime-contract",
         "consumer_revision": "test"},
        {"type": "input", "input": {
            "id": "frame-1", "at_ms": 100, "modality": "video",
            "payload": {"reference_id": "view-1", "image_size": [640, 480],
                        "points": [{"id": "contact", "xy": [0.5, 0.5],
                                    "on_plane": True}]},
        }},
        {"type": "query", "query": "what happened?", "query_ms": 100},
        {"type": "end"},
    ]


async def execute(configuration=CONFIG):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join((str(GAMST_ROOT), str(CREW_ROOT),
                                           str(ROOT), os.environ.get("PYTHONPATH", ""))))
    proc = await asyncio.create_subprocess_exec(
        sys.executable, str(ADAPTER), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    payload = b"".join(json.dumps(message, separators=(",", ":")).encode() + b"\n"
                       for message in messages(configuration))
    stdout, stderr = await proc.communicate(payload)
    rows = [json.loads(line) for line in stdout.splitlines() if line]
    return proc.returncode, rows, stderr.decode()


class CrewRuntimeAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_failure_categories_use_retained_parent_child_state(self):
        adapter = Adapter()
        adapter.phase = "startup"
        self.assertEqual(adapter.failure_category(RuntimeError("bad config")),
                         "startup_failure")
        adapter.phase = "input"
        adapter.bridge = SimpleNamespace(health=lambda: {"running": True})
        adapter.manager = SimpleNamespace(
            runtimes={"runtime": object()},
            health=lambda name: SimpleNamespace(runtime=name, state="ready",
                                                queue_depth=0, capacity=8,
                                                dropped=0, errors=[]),
        )
        self.assertEqual(adapter.failure_category(RuntimeError("provider timeout")),
                         "provider_timeout")
        adapter.bridge = SimpleNamespace(health=lambda: {"running": False,
                                                          "returncode": 1})
        adapter.manager = SimpleNamespace(
            runtimes={"runtime": object()},
            health=lambda name: SimpleNamespace(runtime=name, state="crashed",
                                                queue_depth=0, capacity=8,
                                                dropped=0, errors=["child failed"]),
        )
        self.assertEqual(adapter.failure_category(RuntimeError("submit failed")),
                         "child_crash")

    async def test_real_core_provider_crosses_crew_boundary(self):
        returncode, rows, stderr = await execute()
        self.assertEqual(returncode, 0, stderr)
        self.assertFalse([row for row in rows if row["type"] == "error"])
        ready = next(row for row in rows if row["type"] == "meta" and "ready" in row)
        self.assertTrue(ready["ready"])
        contexts = [row for row in rows if row["type"] == "context"]
        self.assertGreaterEqual(len(contexts), 2)
        packet = contexts[-1]["packet"]
        self.assertTrue(verify_packet_checksum(packet))
        self.assertEqual(packet["capture_timestamp_ms"], 100)
        self.assertEqual(packet["query_cutoff_ms"], 100)
        self.assertEqual(packet["evidence_ids"], ["frame-1"])
        self.assertEqual(packet["clock_id"], ready["health"]["clock_id"])
        self.assertEqual(packet["clock_epoch"], ready["health"]["clock_epoch"])
        self.assertEqual(packet["provider"], "gamst.projective_plane")
        self.assertEqual(rows[-1]["type"], "meta")
        self.assertEqual(rows[-1]["lifecycle"], "stopped")

    async def test_collector_runs_live_runtime_manager_to_bench_trace(self):
        system = copy.deepcopy(CONFIG)
        system.update({"id": "crew-runtime", "name": "Crew runtime",
                       "model": "runtime-contract", "revision": "test",
                       "precision": "not-applicable", "policy": "thin",
                       "role": "primary", "budget_calls": 0,
                       "sampling": "on input", "window": "capture",
                       "hardware": "local CPU", "warm_state": "cold",
                       "budget": "none", "sensor_track": "video"})
        task = {"id": "crew-task", "query": "what happened?", "query_ms": 50,
                "duration_ms": 100, "inputs": [{
                    "id": "frame-1", "at_ms": 0, "modality": "video",
                    "payload": {"reference_id": "view-1", "image_size": [640, 480],
                                "points": [{"id": "contact", "xy": [0.5, 0.5],
                                            "on_plane": True}]},
                }]}
        task["input_sha256"] = digest({"query": task["query"],
                                        "query_ms": task["query_ms"],
                                        "inputs": task["inputs"]})
        plan = {"consumer_model": "runtime-contract", "consumer_revision": "test",
                "evidence": "synthetic", "timeout_ms": 5000,
                "plan_sha256": "p" * 64}
        command = [sys.executable, str(ADAPTER)]
        trace = await run_task(plan, system, task, command)
        self.assertEqual(trace["status"], "success")
        self.assertTrue(trace["packet_checksums"])
        self.assertEqual(trace["query_cutoff_ms"], 50)
        context = next(row for row in trace["outputs"] if row["type"] == "context")
        self.assertEqual(context["evidence_provenance"][0]["id"], "frame-1")
        lifecycle = [row for row in trace["outputs"]
                     if row["type"] == "meta" and row.get("lifecycle") == "stopped"]
        self.assertEqual(len(lifecycle), 1)

    async def test_provider_startup_failure_has_distinct_category(self):
        bad = json.loads(json.dumps(CONFIG))
        bad["runtime"]["provider_config"]["image_to_plane"] = [[0, 0, 0]] * 3
        returncode, rows, _ = await execute(bad)
        self.assertNotEqual(returncode, 0)
        failure = next(row for row in rows if row["type"] == "error")
        self.assertEqual(failure["failure_category"], "startup_failure")


if __name__ == "__main__":
    unittest.main()
