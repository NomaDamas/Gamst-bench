"""StreamArena StreamMind-compatible GAMST extension agent.

Set ``AGENT=gamst_bench.extensions.streamarena_agent:GamstStreamArenaAgent``
for the pinned native ``run_streammind.sh`` launcher.  Frames are queued in
arrival order and all native commits/speaks use the driver's original contract.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from .common import ExtensionConfig, ExtensionSession

try:
    from agent import StreamingAgent  # supplied by StreamArena's native driver
except ImportError:
    class StreamingAgent:  # import/test fallback; native loader uses its own base
        async def start(self, driver):
            self.driver = driver


class GamstStreamArenaAgent(StreamingAgent):
    """Perception never waits on the backbone: frames keep flowing into GAMST
    while at most one frame-triggered VLM call is in flight. Selections made
    during that call are coalesced to the newest one; questions run as their
    own tasks so an answer is never queued behind continuous observation."""

    def __init__(self) -> None:
        self.session = None
        self.queue = None
        self.worker = None
        self.watchers: dict[int, dict[str, Any]] = {}
        self.latest_frame = None
        self.video_id = 0
        self.frame_task = None
        self.pending_selection = None
        self.tasks: set[asyncio.Task] = set()

    async def start(self, driver) -> None:
        await super().start(driver)
        if self.session is not None:
            await self.stop()
            await super().start(driver)
        self.video_id += 1
        self.watchers = {}
        self.latest_frame = None
        self.frame_task = None
        self.pending_selection = None
        self.tasks = set()
        self.session = ExtensionSession(ExtensionConfig.from_env("streamarena"))
        self.queue = asyncio.Queue(maxsize=int(os.environ.get("GAMST_EXTENSION_QUEUE", "16")))
        self.worker = asyncio.create_task(self._run(), name="gamst-streamarena-inputs")

    def _spawn(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def on_frame(self, frame) -> None:
        if self.session is None:
            return
        try:
            self.queue.put_nowait(("frame", float(frame.ts), str(frame.jpeg_b64)))
        except asyncio.QueueFull:
            self.session.sidecar.counts["dropped"] += 1
            self.session.sidecar.write("input_drop", at_sec=float(frame.ts),
                                       reason="bounded_native_queue")

    async def on_audio_observation(self, text: str, video_ts: float) -> None:
        if self.session is not None and text.strip():
            await self.queue.put(("text", float(video_ts), text.strip()))

    async def on_ask(self, qid: int, question: str, qtype: str, video_ts: float) -> None:
        if self.session is not None:
            await self.queue.put(("ask", float(video_ts),
                                  {"qid": qid, "question": question, "qtype": qtype}))

    async def on_e_watch(self, qid: int, question: str, ref_ts: float,
                         deadline_sec: float) -> None:
        if self.session is not None:
            await self.queue.put(("watch", float(ref_ts),
                                  {"qid": qid, "question": question,
                                   "deadline": float(ref_ts) + float(deadline_sec)}))

    async def _run(self) -> None:
        while True:
            kind, at_sec, value = await self.queue.get()
            try:
                if kind == "frame":
                    await self._frame(at_sec, value)
                elif kind == "text":
                    evidence = f"streamarena:{self.video_id}:asr:{at_sec:.3f}"
                    await asyncio.to_thread(self.session.text, evidence, value, at_sec)
                elif kind == "watch":
                    self.watchers[value["qid"]] = value
                elif kind == "ask":
                    await self._ask(at_sec, value)
                elif kind == "stop":
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.session.sidecar.counts["errors"] += 1
                self.session.sidecar.write("agent_error", input_kind=kind,
                                           at_sec=at_sec, error=type(exc).__name__)
                if kind == "ask":
                    await self.driver.commit_answer(value["qid"], "")
            finally:
                self.queue.task_done()

    async def _frame(self, at_sec: float, jpeg_b64: str) -> None:
        evidence = f"streamarena:{self.video_id}:frame:{at_sec:.3f}"
        selection = await asyncio.to_thread(self.session.video, evidence, jpeg_b64, at_sec)
        self.latest_frame = selection
        if not selection["selected"]:
            return
        if self.frame_task is not None and not self.frame_task.done():
            if self.pending_selection is not None:
                self.session.sidecar.write(
                    "selection_coalesced", evidence_ids=[self.pending_selection["evidence_id"]],
                    replaced_by=selection["evidence_id"])
            self.pending_selection = selection
            return
        self.frame_task = self._spawn(self._infer_frames(self.session, selection))

    async def _infer_frames(self, session, selection) -> None:
        while selection is not None:
            try:
                await self._infer_frame(session, selection)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                session.sidecar.counts["errors"] += 1
                session.sidecar.write("agent_error", input_kind="frame",
                                      at_sec=selection["at_sec"], error=type(exc).__name__)
            selection, self.pending_selection = self.pending_selection, None

    async def _infer_frame(self, session, selection) -> None:
        at_sec = selection["at_sec"]
        active = [watch for watch in self.watchers.values() if at_sec <= watch["deadline"]]
        if not active:
            # Continuous semantic memory uses the same selected backbone call.
            await asyncio.to_thread(
                session.infer, selection,
                system_prompt="Describe only newly observable video changes concisely; return an empty response when nothing noteworthy changed.",
                user_text=json.dumps({"timestamp_sec": at_sec}))
            return
        for watch in active:
            text, usage = await asyncio.to_thread(
                session.infer, selection,
                system_prompt=watch["question"] + "\nReturn only the native proactive alert when the watched event has occurred; otherwise return an empty response.",
                user_text=json.dumps({"timestamp_sec": at_sec, "deadline_sec": watch["deadline"]}))
            if text.strip().lower() in {"", "silent", "standby"}:
                continue
            qid = watch["qid"]
            if self.watchers.pop(qid, None) is None:
                continue  # already answered by an earlier call
            session.emit([selection["evidence_id"]], at_sec, text,
                         qid=qid, native_kind="emit_speak", usage=usage)
            await self.driver.emit_speak(qid, text, at_sec)

    async def _ask(self, at_sec: float, request: dict[str, Any]) -> None:
        if self.latest_frame is None:
            await self.driver.commit_answer(request["qid"], "")
            return
        previous = self.latest_frame
        # The question is an explicit GAMST policy query. Only the latest frame
        # at or before the query cutoff is eligible; future frames cannot leak.
        if previous["at_sec"] > at_sec:
            await self.driver.commit_answer(request["qid"], "")
            return
        # Selection stays in input order on the worker; only the call is detached.
        selection = await asyncio.to_thread(
            self.session.video, previous["evidence_id"] + f":ask:{request['qid']}",
            previous["jpeg_b64"], previous["at_sec"], query=True)
        self._spawn(self._answer(self.session, selection, at_sec, request))

    async def _answer(self, session, selection, at_sec: float, request: dict[str, Any]) -> None:
        try:
            text, usage = await asyncio.to_thread(
                session.infer, selection,
                system_prompt="Answer the StreamArena question using only temporal evidence at or before the query cutoff. Be concise and do not speculate.",
                user_text=json.dumps({"question": request["question"], "qtype": request["qtype"],
                                      "query_cutoff_sec": at_sec}))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            session.sidecar.counts["errors"] += 1
            session.sidecar.write("agent_error", input_kind="ask", at_sec=at_sec,
                                  error=type(exc).__name__)
            await self.driver.commit_answer(request["qid"], "")
            return
        session.emit([selection["evidence_id"]], at_sec, text,
                     qid=request["qid"], native_kind="commit_answer", usage=usage)
        await self.driver.commit_answer(request["qid"], text)

    async def stop(self) -> None:
        session, self.session = self.session, None
        if session is None:
            return
        if self.queue is not None:
            await self.queue.put(("stop", 0.0, None))
            await self.queue.join()
        if self.worker is not None:
            await self.worker
            self.worker = None
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        await asyncio.to_thread(session.close)
        self.watchers = {}
        self.latest_frame = None
        self.pending_selection = None
