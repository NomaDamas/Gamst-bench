import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GAMST_ROOT = Path(os.environ.get("GAMST_ROOT", ROOT.parent / "catch-your-mind"))
if str(GAMST_ROOT) not in sys.path:
    sys.path.insert(0, str(GAMST_ROOT))

from gamst_bench.extensions.common import ExtensionConfig, ExtensionSession
from gamst_bench.extensions.fastbench_agent import GamstFastBenchBackend
from gamst_bench.extensions.omnipro_agent import create_streaming_model_class
from gamst_bench.extensions.streamarena_agent import GamstStreamArenaAgent


def jpeg(value=128):
    image = Image.new("RGB", (32, 32), (value, value, value))
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return base64.b64encode(output.getvalue()).decode()


class FakeChat:
    def __init__(self, responses=None):
        self.responses = list(responses or ["observed answer"])
        self.calls = []

    def __call__(self, endpoint, model, messages, allow_remote=False,
                 json_response=False, key_env=None):
        self.calls.append(dict(endpoint=endpoint, model=model, messages=messages,
                               allow_remote=allow_remote, key_env=key_env))
        response = self.responses.pop(0) if self.responses else self.calls[-1]["messages"][-1]["content"]
        if not isinstance(response, str):
            response = "observed answer"
        return response, {"prompt_tokens": 11, "completion_tokens": 3}


def config(directory, benchmark="test", **changes):
    values = dict(benchmark=benchmark, vlm_url="http://127.0.0.1:8080/v1",
                  model="Qwen/Qwen3-VL-8B-Instruct", allow_remote=False,
                  key_env=None, policy="sentinel", semantic_interval_ms=5000,
                  cooldown_ms=0, change_enter=0.08, change_exit=0.03,
                  max_tokens=128, sidecar_path=str(Path(directory) / "sidecar.jsonl"))
    values.update(changes)
    return ExtensionConfig(**values)


class ExtensionSessionTests(unittest.TestCase):
    def test_real_gamst_policy_temporal_cutoff_and_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = FakeChat(["first", "second"])
            session = ExtensionSession(config(directory), chat=chat)
            first = session.video("frame-1", jpeg(), 0.0)
            self.assertTrue(first["selected"])
            text, usage = session.infer(first, system_prompt="system", user_text="observe")
            self.assertEqual(text, "first")
            self.assertEqual(usage["prompt_tokens"], 11)
            unchanged = session.video("frame-2", jpeg(), 0.1)
            self.assertFalse(unchanged["selected"])
            queried = session.video("frame-3", jpeg(), 0.2, query=True)
            self.assertTrue(queried["selected"])
            self.assertIn("explicit_query", queried["decision"]["reason"])
            temporal = session.runtime.call(session.selector.temporal_context(first["capture_ms"]))
            encoded = json.dumps(temporal)
            self.assertIn("frame-1", encoded)
            self.assertNotIn("frame-3", encoded)
            session.infer(queried, system_prompt="system", user_text="answer")
            session.close()
            rows = [json.loads(line) for line in Path(session.sidecar.path).read_text().splitlines()]
            calls = [row for row in rows if row["event"] == "vlm_call"]
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(row["evidence_ids"] for row in calls))
            self.assertTrue(all("vlm_call_started_unix_ms" in row for row in calls))
            self.assertTrue(all("time_to_detect_ms" in row for row in calls))
            self.assertEqual(rows[-1]["counts"]["vlm_calls"], 2)
            self.assertEqual(len(chat.calls), 2)

    def test_replay_faster_than_wall_clock_keeps_all_observations(self):
        # Benchmarks replay hours of media in seconds; GAMST rejects records
        # more than 5 s ahead of wall clock, so media time must stay causal and past.
        with tempfile.TemporaryDirectory() as directory:
            session = ExtensionSession(config(directory), chat=FakeChat())
            late = session.video("frame-late", jpeg(10), 3 * 3600.0)
            later = session.video("frame-later", jpeg(240), 3 * 3600.0 + 30.0)
            self.assertTrue(later["selected"])
            temporal = session.runtime.call(
                session.selector.temporal_context(later["capture_ms"]))
            self.assertIn("frame-late", json.dumps(temporal))
            self.assertLess(late["capture_ms"], later["capture_ms"])
            session.close()


class DecodeVideoChunkTests(unittest.TestCase):
    def test_sequential_decode_returns_requested_timestamps(self):
        import cv2
        from gamst_bench.extensions.common import decode_video_chunk

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "clip.avi")
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (32, 32))
            for index in range(30):
                writer.write(np.full((32, 32, 3), index * 8, dtype=np.uint8))
            writer.release()
            frames = decode_video_chunk(path, 20.0, 1.0, 2.0)
            self.assertEqual([round(at, 3) for at, _ in frames], [20.0, 20.5])
            brightness = [np.asarray(Image.open(io.BytesIO(base64.b64decode(data)))).mean()
                          for _, data in frames]
            # Second sample is frame 15 (0.5 s at 30 fps), not a repeat of frame 0.
            self.assertAlmostEqual(brightness[1] - brightness[0], 15 * 8, delta=6)


class DummyStreamingBase:
    pass


class OmniProExtensionTests(unittest.TestCase):
    def test_observe_consumes_audio_and_emits_native_raw_text(self):
        with tempfile.TemporaryDirectory() as directory:
            chat = FakeChat(["4"])
            cls = create_streaming_model_class(DummyStreamingBase)
            with patch("gamst_bench.extensions.omnipro_agent.ExtensionConfig.from_env",
                       return_value=config(directory, "omnipro")):
                model = cls(chat=chat)
            model.begin("native instruction", {"id": "sample", "task": "snapshot_counting",
                                               "question": "count", "ground_truth": ["do-not-send"]})
            raw = model.observe(np.zeros((32, 32, 3), dtype=np.uint8), 0.0, [],
                                np.zeros(16000, dtype=np.float32))
            self.assertEqual(raw, "4")
            prompt = chat.calls[0]["messages"][1]["content"][0]["text"]
            self.assertNotIn("do-not-send", prompt)
            self.assertEqual(chat.calls[0]["messages"][0]["content"], "native instruction")
            model.end()
            events = [json.loads(line)["event"] for line in
                      Path(model.session.sidecar.path).read_text().splitlines()]
            self.assertIn("audio", events)
            self.assertIn("native_emit", events)
            # The native evaluator reuses one model instance for every sample.
            chat.responses = ["7"]
            model.begin("native instruction", {"id": "second", "task": "snapshot_counting",
                                               "question": "count"})
            self.assertEqual(model.observe(np.full((32, 32, 3), 200, dtype=np.uint8), 0.0, []), "7")
            model.end()


class FastBenchExtensionTests(unittest.TestCase):
    def test_backend_returns_native_response_and_only_calls_after_selection(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("gamst_bench.extensions.fastbench_agent.ExtensionConfig.from_env",
                      return_value=config(directory, "fastbench")), \
                patch("gamst_bench.extensions.fastbench_agent.decode_video_chunk",
                      return_value=[(0.0, jpeg())]):
            chat = FakeChat(["B"])
            backend = GamstFastBenchBackend("qwen3_vl", {
                "model": "Qwen/Qwen3-VL-8B-Instruct", "api_base": "http://127.0.0.1:8080/v1",
            }, chat=chat)
            result = backend.generate([
                {"role": "system", "content": [{"type": "text", "text": "native system"}]},
                {"role": "user", "content": [
                    {"type": "video", "video": "chunk.mp4", "sample_id": "sample",
                     "chunk_start_seconds": 0, "chunk_duration_seconds": 1, "fps": 2},
                    {"type": "text", "text": "Question: choose\nOptions: A,B"},
                ]},
            ])
            self.assertEqual(result["status_code"], 200)
            self.assertEqual(result["response"], "B")
            self.assertEqual(len(chat.calls), 1)
            self.assertEqual(chat.calls[0]["messages"][0]["content"], "native system")
            backend.close()


class FakeDriver:
    def __init__(self):
        self.answers = []
        self.speaks = []

    async def commit_answer(self, qid, text):
        self.answers.append((qid, text))

    async def emit_speak(self, qid, text, video_ts):
        self.speaks.append((qid, text, video_ts))


class StreamArenaExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_callbacks_commit_and_speak_in_causal_order(self):
        with tempfile.TemporaryDirectory() as directory:
            # Calls run concurrently, so responses follow the prompt, not call order.
            def chat(endpoint, model, messages, allow_remote=False, json_response=False,
                     key_env=None):
                system = messages[0]["content"]
                if system.startswith("watch for event"):
                    return "event happened", {}
                if system.startswith("Answer the StreamArena"):
                    return "final answer", {}
                return "memory", {}

            def session_factory(_):
                return ExtensionSession(config(directory, "streamarena", semantic_interval_ms=1), chat=chat)

            with patch("gamst_bench.extensions.streamarena_agent.ExtensionSession", session_factory):
                agent = GamstStreamArenaAgent()
                driver = FakeDriver()
                await agent.start(driver)
                await agent.on_frame(SimpleNamespace(ts=0.0, jpeg_b64=jpeg()))
                await agent.queue.join()
                await agent.on_e_watch(1, "watch for event", 1.0, 5.0)
                await agent.on_frame(SimpleNamespace(ts=1.0, jpeg_b64=jpeg(255)))
                await agent.on_ask(2, "what happened?", "a", 1.0)
                await agent.queue.join()
                await agent.stop()
            self.assertEqual(driver.speaks, [(1, "event happened", 1.0)])
            self.assertEqual(driver.answers, [(2, "final answer")])

    async def test_frames_keep_flowing_while_backbone_call_is_in_flight(self):
        import threading

        release = threading.Event()
        calls = []

        def blocked_chat(endpoint, model, messages, allow_remote=False,
                         json_response=False, key_env=None):
            calls.append(messages)
            release.wait(10)
            return "", {}

        with tempfile.TemporaryDirectory() as directory:
            def session_factory(_):
                return ExtensionSession(config(directory, "streamarena", semantic_interval_ms=1),
                                        chat=blocked_chat)

            with patch("gamst_bench.extensions.streamarena_agent.ExtensionSession", session_factory):
                agent = GamstStreamArenaAgent()
                await agent.start(FakeDriver())
                for index in range(12):
                    await agent.on_frame(SimpleNamespace(ts=index * 0.5, jpeg_b64=jpeg(index * 20)))
                # Perception must drain even though the first VLM call never returns.
                await asyncio.wait_for(agent.queue.join(), timeout=5)
                counts = dict(agent.session.sidecar.counts)
                release.set()
                await agent.stop()
            self.assertEqual(counts["dropped"], 0)
            self.assertEqual(counts["inputs"], 12)
            # One call in flight; only the newest pending selection runs after it.
            self.assertLessEqual(len(calls), 2)


class ExtensionTemplateTests(unittest.TestCase):
    def test_profiles_are_distinct_and_commands_cover_all_arms(self):
        profiles = json.loads((ROOT / "mcp" / "profiles.example.json").read_text())["profiles"]
        for benchmark in ("fastbench", "omnipro", "streamarena"):
            profile = profiles[f"{benchmark}-gamst-extension"]
            self.assertEqual(profile["track"], "gamst-extension")
            self.assertFalse(profile["enabled"])
            self.assertNotEqual(profile["mode"], f"{benchmark}-continuous")
        commands = json.loads((ROOT / "runs" / "experiment-template" / "commands.json").read_text())
        self.assertEqual(set(commands), {"A", "B", "C", "D", "E", "F", "C-jev"})
        self.assertIn("8080", json.dumps(commands["A"]))
        self.assertIn("8081", json.dumps(commands["E"]))
        self.assertEqual(commands["F"][1:3], ["-m", "gamst_bench.adapters.gemini_live"])


if __name__ == "__main__":
    unittest.main()
