"""FastBench native-runner backend with causal GAMST VLM selection.

Run through this module (or the thin shim documented in docs/EXTENSIONS.md).
The pinned FastBench checkout is imported read-only; only build_backend is
replaced in memory for entries whose config declares ``backend: gamst``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .common import ExtensionConfig, ExtensionSession, decode_video_chunk


class GamstFastBenchBackend:
    """Drop-in ``generate`` result contract used by FastBench SessionModel."""

    def __init__(self, name: str, cfg: dict[str, Any], *, chat=None):
        self.name = name
        self.model = str(cfg.get("model", "Qwen/Qwen3-VL-8B-Instruct"))
        self.api_base = str(cfg.get("api_base", "http://127.0.0.1:8080/v1")).rstrip("/")
        self.api_key = ""
        self.max_retries = 1  # persistent policy state is not safely replayable
        self.timeout = float(cfg.get("timeout", 120))
        self.max_new_tokens = int(cfg.get("max_new_tokens", 256))
        self.config = ExtensionConfig.from_env(
            "fastbench", vlm_url=self.api_base, model=self.model)
        self._chat = chat
        self.session = None
        self.sample_id = None
        self.latest_frame = None

    def _start(self, sample_id: str) -> None:
        if self.session is not None and self.sample_id == sample_id:
            return
        self.close()
        self.sample_id = sample_id
        kwargs = {} if self._chat is None else {"chat": self._chat}
        self.session = ExtensionSession(self.config, **kwargs)
        self.latest_frame = None
        self.active_question = False

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content
        return "\n".join(str(item.get("text", "")) for item in content or []
                         if isinstance(item, dict) and item.get("type") == "text")

    def generate(self, messages: list[dict[str, Any]], max_new_tokens: int | None = None,
                 **_: Any) -> dict[str, Any]:
        users = [message for message in messages if message.get("role") == "user"]
        if not users:
            return {"response": "Silent", "raw_response": "Silent", "status_code": 200}
        current = users[-1]
        content = current.get("content", [])
        video = next((item for item in content if item.get("type") == "video"), None)
        sample_id = str((video or {}).get("sample_id") or "fastbench-session")
        self._start(sample_id)
        system = "\n".join(self._text(message.get("content")) for message in messages
                           if message.get("role") == "system")
        # Textual dialogue is retained exactly; old pixels are represented only
        # by GAMST temporal evidence and newly selected frames.
        dialogue = [{"role": message.get("role"), "text": self._text(message.get("content"))}
                    for message in messages if message.get("role") != "system"]
        new_text = self._text(content)
        if "Question:" in new_text:
            self.active_question = True
        query = bool(getattr(self, "active_question", False))
        observations = []
        try:
            if video is not None:
                start = float(video.get("chunk_start_seconds", 0.0))
                duration = float(video.get("chunk_duration_seconds", 1.0))
                fps = float(video.get("fps", 2.0))
                frames = decode_video_chunk(str(video["video"]), start, duration, fps)
                # ProactiveFrame focus re-sends an already-streamed window at a
                # higher FPS. GAMST memory is causal and already holds that
                # window, so only frames past the newest observation are new input.
                horizon = self.latest_frame["at_sec"] if self.latest_frame is not None else -1.0
                fresh = [(index, at_sec, jpeg) for index, (at_sec, jpeg) in enumerate(frames)
                         if at_sec > horizon]
                if len(fresh) < len(frames):
                    self.session.sidecar.write("replayed_frames_skipped", sample_id=sample_id,
                                               chunk_start_sec=start,
                                               skipped=len(frames) - len(fresh))
                for index, at_sec, jpeg in fresh:
                    evidence = f"fastbench:{sample_id}:{start:.3f}:{index}"
                    selection = self.session.video(evidence, jpeg, at_sec, query=query)
                    observations.append(selection)
                    self.latest_frame = selection
            if not observations and self.latest_frame is not None:
                # Question-only or replay-only native steps still cause an explicit policy query.
                previous = self.latest_frame
                observations.append(self.session.video(
                    previous["evidence_id"] + ":query", previous["jpeg_b64"],
                    previous["at_sec"], query=True))
            response = "Silent"
            raw_usage: dict[str, Any] = {}
            answered = False
            for selection in observations:
                if not selection["selected"]:
                    continue
                text, usage = self.session.infer(
                    selection, system_prompt=system,
                    user_text=json.dumps({"native_dialogue": dialogue}, ensure_ascii=False))
                raw_usage = usage
                candidate = text.strip() or "Silent"
                if candidate.lower() != "silent":
                    response = candidate
                    if candidate.lower() not in {"focus_start", "focus_end"}:
                        answered = True
            if answered:
                self.active_question = False
                evidence = [item["evidence_id"] for item in observations]
                self.session.emit(evidence, observations[-1]["at_sec"], response,
                                  sample_id=sample_id, usage=raw_usage)
            return {"response": response, "raw_response": response,
                    "status_code": 200, "usage": raw_usage}
        except Exception as exc:
            self.session.sidecar.counts["errors"] += 1
            self.session.sidecar.write("backend_error", sample_id=sample_id,
                                       error=type(exc).__name__)
            return {"response": f"[ERROR] {type(exc).__name__}: {exc}",
                    "raw_response": "", "status_code": 502}

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None


def install(run_stream_eval: Any) -> list[GamstFastBenchBackend]:
    """Patch only the in-memory native backend factory and return owned instances."""
    original = run_stream_eval.build_backend
    owned: list[GamstFastBenchBackend] = []

    def build(name: str, cfg: dict[str, Any]):
        selected = os.environ.get("GAMST_EXTENSION_FASTBENCH_MODEL")
        if (str(cfg.get("backend", "")).strip().lower() in {"gamst", "gamst_extension"}
                or selected == name):
            backend = GamstFastBenchBackend(name, cfg)
            owned.append(backend)
            return backend
        return original(name, cfg)

    run_stream_eval.build_backend = build
    return owned


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastbench-root", required=True)
    parser.add_argument("native_args", nargs=argparse.REMAINDER,
                        help="arguments after -- are passed unchanged to run_stream_eval.py")
    args = parser.parse_args(argv)
    root = Path(args.fastbench_root).expanduser().resolve()
    if not (root / "run_stream_eval.py").is_file():
        parser.error("FastBench checkout must contain run_stream_eval.py")
    sys.path.insert(0, str(root))
    import run_stream_eval
    import run_stream_eval_parallel

    owned = install(run_stream_eval)
    native = list(args.native_args)
    if native and native[0] == "--":
        native.pop(0)
    sys.argv = [str(root / "run_stream_eval.py"), *native]
    try:
        run_stream_eval_parallel.main()
    finally:
        for backend in owned:
            backend.close()


if __name__ == "__main__":
    main()
