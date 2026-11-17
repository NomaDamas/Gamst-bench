"""OmniPro ``StreamingModel`` with GAMST selection and matched HTTP VLM.

Audio chunks are consumed causally into GAMST as measured energy. Qwen3-VL has
no PCM input; this adapter never invents a transcript or claims audio semantics.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .common import ExtensionConfig, ExtensionSession, encode_jpeg


def create_streaming_model_class(streaming_base: type):
    """Create a class satisfying OmniPro's runtime ``isinstance`` check."""

    class GamstOmniProStreaming(streaming_base):
        accepts_audio = True
        native_fps = 1.0

        def __init__(self, model_path: str | None = None, device: str = "cpu",
                     max_new_speak_tokens: int = 128, *, chat=None, **_: Any):
            # model_path is retained in the native CLI for interface parity; the
            # served checkpoint name is selected independently by --model/env.
            config = ExtensionConfig.from_env(
                "omnipro", model=(model_path if model_path and "/" in model_path
                                  and not Path(model_path).exists() else None))
            if max_new_speak_tokens:
                config = ExtensionConfig(**{**config.__dict__,
                                            "max_tokens": int(max_new_speak_tokens)})
            kwargs = {} if chat is None else {"chat": chat}
            self.session = ExtensionSession(config, **kwargs)
            self.instruction = ""
            self.task = ""
            self.question = ""
            self.sample_id = "omnipro"
            self.closed = False

        def name(self) -> str:
            return f"GAMST-Extension-OmniPro-{self.session.config.model}"

        def begin(self, instruction: str, task_meta: dict[str, Any]) -> None:
            self.instruction = instruction
            self.task = str(task_meta.get("task", ""))
            self.question = str(task_meta.get("question", ""))
            self.sample_id = str(task_meta.get("id", "omnipro"))
            self.session.sidecar.write("native_begin", native_sample_id=self.sample_id,
                                       task=self.task)

        def observe(self, frame, t_sec: float, history: list[dict[str, Any]],
                    audio_chunk=None) -> str | None:
            if self.closed:
                raise RuntimeError("observe after end")
            evidence_base = f"omnipro:{self.sample_id}:{t_sec:.3f}"
            if audio_chunk is not None:
                self.session.audio(evidence_base + ":audio", audio_chunk, t_sec)
            if frame is None:
                return None
            jpeg = encode_jpeg(frame)
            selection = self.session.video(evidence_base + ":video", jpeg, t_sec)
            if not selection["selected"]:
                return None
            user = json.dumps({
                "task": self.task, "question": self.question, "timestamp_sec": t_sec,
                "native_history": history,
                "output_contract": "Return the native OmniPro emit only. Return an empty response for STANDBY; never explain silence.",
            }, ensure_ascii=False)
            text, usage = self.session.infer(
                selection, system_prompt=self.instruction, user_text=user)
            if text.strip().lower() in {"", "silent", "standby", "</silence>", "</standby>"}:
                return None
            self.session.emit([selection["evidence_id"]], t_sec, text,
                              native_sample_id=self.sample_id, task=self.task, usage=usage)
            return text

        def end(self) -> None:
            if not self.closed:
                self.closed = True
                self.session.close()

    return GamstOmniProStreaming


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--omnipro-root", required=True)
    parser.add_argument("native_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    root = Path(args.omnipro_root).expanduser().resolve()
    runner = root / "scripts" / "run_online.py"
    if not runner.is_file():
        parser.error("OmniPro checkout must contain scripts/run_online.py")
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "scripts"))
    import run_online
    from models.streaming_base import StreamingModel

    gamst_class = create_streaming_model_class(StreamingModel)
    original_build = run_online.build_model

    def build(native_args, device):
        if native_args.model in {"gamst", "gamst-extension"}:
            return gamst_class(model_path=native_args.model_path, device=device,
                               max_new_speak_tokens=native_args.max_new_speak_tokens or 128)
        return original_build(native_args, device)

    native = list(args.native_args)
    if native and native[0] == "--":
        native.pop(0)
    # Preserve the pinned parser and every native option while adding one model
    # name without editing the upstream checkout.
    substituted = list(native)
    for index, value in enumerate(substituted[:-1]):
        if value == "--model" and substituted[index + 1] in {"gamst", "gamst-extension"}:
            substituted[index + 1] = "dummy-perfect"
    sys.argv = [str(runner), *substituted]
    original_parse = run_online.parse_args

    def parse():
        parsed = original_parse()
        for index, value in enumerate(native[:-1]):
            if value == "--model" and native[index + 1] in {"gamst", "gamst-extension"}:
                parsed.model = native[index + 1]
        return parsed

    run_online.parse_args = parse
    run_online.build_model = build
    run_online.main()


if __name__ == "__main__":
    main()
