"""Shared causal GAMST selection, OpenAI VLM calls, and native-run sidecars.

No function in this module fabricates detections or token usage.  Video change
scores are measured thumbnails; audio energy is only a non-semantic feature.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from gamst_bench.adapters.gamst_http import request_chat


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ExtensionConfig:
    benchmark: str
    vlm_url: str
    model: str
    allow_remote: bool
    key_env: str | None
    policy: str
    semantic_interval_ms: int
    cooldown_ms: int
    change_enter: float
    change_exit: float
    max_tokens: int
    sidecar_path: str

    @classmethod
    def from_env(cls, benchmark: str, *, vlm_url: str | None = None,
                 model: str | None = None) -> "ExtensionConfig":
        prefix = "GAMST_EXTENSION_"
        return cls(
            benchmark=benchmark,
            vlm_url=vlm_url or os.environ.get(prefix + "VLM_URL", "http://127.0.0.1:8080/v1"),
            model=model or os.environ.get(prefix + "MODEL", "Qwen/Qwen3-VL-8B-Instruct"),
            allow_remote=env_bool(prefix + "ALLOW_REMOTE"),
            key_env=os.environ.get(prefix + "VLM_KEY_ENV") or None,
            policy=os.environ.get(prefix + "POLICY", "sentinel"),
            semantic_interval_ms=int(os.environ.get(prefix + "SEMANTIC_INTERVAL_MS", "5000")),
            cooldown_ms=int(os.environ.get(prefix + "COOLDOWN_MS", "1000")),
            change_enter=float(os.environ.get(prefix + "CHANGE_ENTER", "0.08")),
            change_exit=float(os.environ.get(prefix + "CHANGE_EXIT", "0.03")),
            max_tokens=int(os.environ.get(prefix + "MAX_TOKENS", "256")),
            sidecar_path=os.environ.get(
                prefix + "SIDECAR", f"{benchmark}-gamst-extension-{os.getpid()}.jsonl"),
        )


class Sidecar:
    """Thread-safe JSONL evidence; media and credentials are never written."""

    def __init__(self, path: str, benchmark: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.benchmark = benchmark
        self.session_id = uuid.uuid4().hex
        self.evidence_class = os.environ.get("GAMST_EXTENSION_EVIDENCE_CLASS", "smoke")
        if self.evidence_class not in {"smoke", "measured", "synthetic"}:
            raise ValueError("GAMST_EXTENSION_EVIDENCE_CLASS must be smoke, measured, or synthetic")
        self.lock = threading.Lock()
        self.counts = {"inputs": 0, "selected": 0, "vlm_calls": 0,
                       "emits": 0, "dropped": 0, "errors": 0}
        self.write("session_start", evidence_class=self.evidence_class)

    def write(self, event: str, **fields: Any) -> None:
        row = {"event": event, "benchmark": self.benchmark,
               "session_id": self.session_id, "evidence_class": self.evidence_class,
               "logged_at_unix_ms": int(time.time() * 1000), **fields}
        with self.lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                        separators=(",", ":")) + "\n")

    def close(self) -> None:
        self.write("session_summary", counts=dict(self.counts))


def encode_jpeg(frame: Any) -> str:
    """Encode an OmniPro HWC RGB array without importing a model framework."""
    from PIL import Image
    import numpy as np

    array = np.asarray(frame)
    if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("OmniPro frame must be uint8 HWC RGB")
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="JPEG", quality=90)
    return base64.b64encode(output.getvalue()).decode("ascii")


def decode_video_chunk(path: str, start_sec: float, duration_sec: float,
                       fps: float) -> list[tuple[float, str]]:
    """Decode chronological JPEG frames; no center sampling or future frames."""
    import cv2

    if fps <= 0 or duration_sec < 0:
        raise ValueError("positive fps and nonnegative chunk duration required")
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise ValueError(f"cannot open video chunk: {path}")
    frames: list[tuple[float, str]] = []
    try:
        count = max(1, int(round(duration_sec * fps))) if duration_sec else 1
        for index in range(count):
            offset = min(index / fps, max(0.0, duration_sec - 1e-6))
            capture.set(cv2.CAP_PROP_POS_MSEC, offset * 1000.0)
            ok, frame = capture.read()
            if not ok:
                break
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                raise ValueError("JPEG encoding failed")
            frames.append((start_sec + offset,
                           base64.b64encode(encoded.tobytes()).decode("ascii")))
    finally:
        capture.release()
    return frames


def thumbnail(jpeg_b64: str) -> bytes:
    from PIL import Image

    raw = base64.b64decode(jpeg_b64, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        return image.convert("L").resize((16, 16)).tobytes()


def change_score(previous: bytes | None, current: bytes) -> float:
    if previous is None:
        return 1.0
    return sum(abs(a - b) for a, b in zip(previous, current)) / (255.0 * len(current))


class GamstSelector:
    """Real Gamst records + CallPolicy decisions on one asyncio event loop."""

    def __init__(self, config: ExtensionConfig, sidecar: Sidecar):
        self.config = config
        self.sidecar = sidecar
        self.human = None
        self.policy = None
        self.capture_origin_ms = int(time.time() * 1000)
        self.sequence = 0
        self.stream_epoch = uuid.uuid4().hex
        self.previous_thumbnail = None
        self.change_active = False
        self.last_dispatch_ms = None
        self.last_semantic_capture_ms = None
        self.last_capture_ms = -1

    async def start(self) -> None:
        try:
            from gamst import CapabilitySpec, Gamst, OutputField
            from gamst.call_policy import CallPolicy
        except ImportError as exc:
            raise RuntimeError(
                "GAMST checkout is required; set PYTHONPATH to catch-your-mind") from exc
        self.human = Gamst(consent=True, retention_hours=0.01,
                           window_ms=max(30_000, self.config.semantic_interval_ms * 4),
                           sensor_inference_interval_ms=5000)
        await self.human.__aenter__()
        common = dict(provider="gamst-bench.extension", version="1",
                      streaming_mode="frame", freshness_ms=60_000,
                      interpretation="measurement")
        self.human.register_capability(CapabilitySpec(
            id="gamst-bench.video-change", output_name="stream.video_change",
            modality="video", fields=(OutputField("change_score", "number"),
                                      OutputField("evidence_ids", "array")), **common))
        self.human.register_capability(CapabilitySpec(
            id="gamst-bench.audio-energy", output_name="stream.audio_energy",
            modality="audio", fields=(OutputField("rms", "number"),
                                      OutputField("evidence_ids", "array")), **common))
        self.policy = CallPolicy(
            mode=self.config.policy,
            semantic_interval_ms=self.config.semantic_interval_ms,
            cooldown_ms=self.config.cooldown_ms, max_age_ms=60_000,
            change_enter=self.config.change_enter, change_exit=self.config.change_exit)

    def capture_ms(self, at_sec: float) -> int:
        if at_sec < 0:
            raise ValueError("causal nonnegative media timestamp required")
        return self.capture_origin_ms + int(round(at_sec * 1000.0))

    def _sensor(self, modality: str):
        from gamst import SensorMetadata
        return SensorMetadata("gamst-bench", modality, self.sequence,
                              stream_epoch=self.stream_epoch,
                              capture_sequence=self.sequence,
                              clock_id="benchmark-video", clock_epoch=self.stream_epoch)

    async def observe_video(self, evidence_id: str, jpeg_b64: str, at_sec: float,
                            *, query: bool = False) -> dict[str, Any]:
        current = thumbnail(jpeg_b64)
        score = change_score(self.previous_thumbnail, current)
        self.previous_thumbnail = current
        capture = self.capture_ms(at_sec)
        if capture < self.last_capture_ms:
            raise ValueError("input timestamps must be causal")
        self.last_capture_ms = capture
        self.sequence += 1
        record = await self.human.push_signal(
            "stream.video_change", {"change_score": score, "evidence_ids": [evidence_id]},
            "video", timestamp_ms=capture, model_id="gamst-bench.extension",
            model_version="1", quality="sufficient",
            capability_id="gamst-bench.video-change", sensor=self._sensor("video"))
        decision = self.policy.recommend(
            record, now_ms=capture, change_score=score,
            change_active=self.change_active, last_dispatch_ms=self.last_dispatch_ms,
            last_semantic_capture_ms=self.last_semantic_capture_ms,
            query=query, needs_visual=True,
            visual_reference={"source_id": "gamst-bench", "sensor_id": "video",
                              "stream_epoch": self.stream_epoch, "capture_ms": capture,
                              "sha256": hashlib.sha256(base64.b64decode(jpeg_b64)).hexdigest()})
        self.change_active = decision["proposed_change_active"]
        selected = decision["recommended_route"] in {"small_vlm", "strong_vlm"}
        self.sidecar.counts["inputs"] += 1
        self.sidecar.counts["selected"] += int(selected)
        self.sidecar.write("selection", evidence_ids=[evidence_id], capture_ms=capture,
                           change_score=score, query=query, decision=decision)
        return {"selected": selected, "evidence_id": evidence_id, "jpeg_b64": jpeg_b64,
                "capture_ms": capture, "at_sec": at_sec, "decision": decision}

    async def observe_audio(self, evidence_id: str, samples: Any, at_sec: float) -> None:
        import numpy as np
        array = np.asarray(samples, dtype=np.float32).reshape(-1)
        rms = float(np.sqrt(np.mean(np.square(array, dtype=np.float64)))) if array.size else 0.0
        capture = self.capture_ms(at_sec)
        if capture < self.last_capture_ms:
            raise ValueError("audio/video timestamps must be causal")
        self.last_capture_ms = capture
        self.sequence += 1
        await self.human.push_signal(
            "stream.audio_energy", {"rms": rms, "evidence_ids": [evidence_id]},
            "audio", timestamp_ms=capture, model_id="gamst-bench.extension",
            model_version="1", quality="sufficient",
            capability_id="gamst-bench.audio-energy", sensor=self._sensor("audio"))
        self.sidecar.counts["inputs"] += 1
        self.sidecar.write("audio", evidence_ids=[evidence_id], capture_ms=capture,
                           rms=rms, interpretation="non_semantic_energy_only")

    async def observe_text(self, evidence_id: str, text: str, at_sec: float) -> None:
        capture = self.capture_ms(at_sec)
        # StreamArena ASR can arrive late with an earlier interval-end timestamp.
        # Keep that original capture time; do not reorder future frames into it.
        self.sequence += 1
        await self.human.push_signal(
            "stream.semantic", {"description": text[:8192], "evidence_ids": [evidence_id]},
            "text", timestamp_ms=capture, model_id="streamarena.asr", model_version="external",
            quality="sufficient")
        self.sidecar.counts["inputs"] += 1

    async def add_semantic(self, description: str, evidence_ids: list[str], capture_ms: int) -> None:
        self.sequence += 1
        await self.human.push_signal(
            "stream.semantic", {"description": description[:8192], "evidence_ids": evidence_ids},
            "text", timestamp_ms=capture_ms, model_id=self.config.model,
            model_version="configured-pinned-revision", quality="sufficient")

    async def temporal_context(self, query_cutoff_ms: int) -> dict[str, Any]:
        return await self.human.build_temporal_context(
            query_cutoff_ms=query_cutoff_ms, max_bytes=96 * 1024)

    def mark_dispatched(self, capture_ms: int) -> None:
        self.last_dispatch_ms = capture_ms
        self.last_semantic_capture_ms = capture_ms

    async def close(self) -> None:
        if self.human is not None:
            await self.human.__aexit__(None, None, None)
            self.human = None


class SyncRuntime:
    """Own a persistent event-loop thread for synchronous native model APIs."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name="gamst-extension-loop")
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=10)
        self.loop.close()


class ExtensionSession:
    """Synchronous front-end used by FastBench/OmniPro and via threads by StreamArena."""

    def __init__(self, config: ExtensionConfig, chat: Callable[..., Any] = request_chat):
        self.config = config
        self.sidecar = Sidecar(config.sidecar_path, config.benchmark)
        self.runtime = SyncRuntime()
        self.selector = GamstSelector(config, self.sidecar)
        self.chat = chat
        self.closed = False
        self.runtime.call(self.selector.start())

    def video(self, evidence_id: str, jpeg_b64: str, at_sec: float, *, query: bool = False):
        return self.runtime.call(self.selector.observe_video(
            evidence_id, jpeg_b64, at_sec, query=query))

    def audio(self, evidence_id: str, samples: Any, at_sec: float) -> None:
        self.runtime.call(self.selector.observe_audio(evidence_id, samples, at_sec))

    def text(self, evidence_id: str, text: str, at_sec: float) -> None:
        self.runtime.call(self.selector.observe_text(evidence_id, text, at_sec))

    def infer(self, selection: dict[str, Any], *, system_prompt: str,
              user_text: str, extra_frames: list[dict[str, Any]] | None = None) -> tuple[str, dict[str, Any]]:
        """Call the configured backbone only after a real policy recommendation."""
        if not selection.get("selected"):
            return "", {}
        frames = [selection, *(extra_frames or [])]
        frames.sort(key=lambda item: item["capture_ms"])
        cutoff = selection["capture_ms"]
        temporal = self.runtime.call(self.selector.temporal_context(cutoff))
        content = [{"type": "text", "text": json.dumps({
            "instruction": user_text, "query_cutoff_ms": cutoff,
            "gamst_temporal_context": temporal,
        }, ensure_ascii=False)}]
        for frame in frames:
            content.append({"type": "text", "text": (
                f"Evidence {frame['evidence_id']} captured at {frame['at_sec']:.3f}s; "
                "frames are chronological and none is after the query cutoff.")})
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + frame["jpeg_b64"]}})
        started = time.time()
        self.sidecar.counts["vlm_calls"] += 1
        call_index = self.sidecar.counts["vlm_calls"]
        try:
            text, usage = self.chat(
                self.config.vlm_url, self.config.model,
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": content}],
                self.config.allow_remote, False, key_env=self.config.key_env)
        except Exception as exc:
            self.sidecar.counts["errors"] += 1
            self.sidecar.write("vlm_error", call_index=call_index,
                               evidence_ids=[selection["evidence_id"]], error=type(exc).__name__)
            raise
        ended = time.time()
        evidence_ids = [frame["evidence_id"] for frame in frames]
        self.sidecar.write(
            "vlm_call", call_index=call_index, evidence_ids=evidence_ids,
            vlm_call_started_at=started, vlm_call_completed_at=ended,
            vlm_call_started_unix_ms=int(started * 1000),
            vlm_call_completed_unix_ms=int(ended * 1000),
            time_to_detect_ms=max(0, int(ended * 1000) - cutoff), usage=usage)
        self.selector.mark_dispatched(cutoff)
        self.runtime.call(self.selector.add_semantic(text, evidence_ids, cutoff))
        return text.strip(), usage

    def emit(self, evidence_ids: list[str], at_sec: float, native_output: str,
             **fields: Any) -> None:
        self.sidecar.counts["emits"] += 1
        self.sidecar.write("native_emit", evidence_ids=evidence_ids,
                           capture_ms=self.selector.capture_ms(at_sec),
                           native_output=native_output[:8192], **fields)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.runtime.call(self.selector.close())
        finally:
            self.runtime.close()
            self.sidecar.close()
