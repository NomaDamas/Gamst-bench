"""JSONL adapter for one real GamstCrew-managed GAMST Core provider.

This adapter is deliberately small: the bench collector owns scheduling and
trace accounting while Crew owns the provider process lifecycle.  The first
supported provider is the dependency-free ``geometry.ground_plane`` profile;
the path is runtime-contract evidence and does not make model-quality claims.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any


def _add_import_roots(configuration: dict[str, Any]) -> tuple[str, str]:
    runtime = configuration.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("start.configuration.runtime is required")
    gamst_root = runtime.get("gamst_root")
    crew_root = runtime.get("crew_root")
    if not isinstance(gamst_root, str) or not gamst_root:
        raise ValueError("runtime.gamst_root is required")
    if not isinstance(crew_root, str) or not crew_root:
        raise ValueError("runtime.crew_root is required")
    gamst_root = str(Path(gamst_root).expanduser().resolve())
    crew_root = str(Path(crew_root).expanduser().resolve())
    for root in (gamst_root, crew_root):
        if not Path(root).is_dir():
            raise ValueError("runtime import root does not exist")
        if root not in sys.path:
            sys.path.insert(0, root)
    old = os.environ.get("PYTHONPATH", "")
    roots = [gamst_root, crew_root]
    if old:
        roots.append(old)
    os.environ["PYTHONPATH"] = os.pathsep.join(roots)
    return gamst_root, crew_root


def _runtime_configuration(configuration: dict[str, Any]) -> tuple[dict[str, Any], str, str, str]:
    runtime = configuration["runtime"]
    profile = runtime.get("profile")
    python = runtime.get("python")
    provider_config = runtime.get("provider_config")
    if not isinstance(profile, str) or not profile:
        raise ValueError("runtime.profile is required")
    if not isinstance(python, str) or not python:
        raise ValueError("runtime.python is required")
    executable = str(Path(python).expanduser().absolute())
    if not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise ValueError("runtime.python must be an executable file")
    if not isinstance(provider_config, dict):
        raise ValueError("runtime.provider_config must be an object")
    name = runtime.get("name", profile)
    if not isinstance(name, str) or not name:
        raise ValueError("runtime.name must be a non-empty string")
    return provider_config, executable, profile, name


def _input_packet(message: dict[str, Any], *, sequence: int, subject_id: str,
                  source_id: str, sensor_id: str):
    """Turn one frozen bench input into a checksummed Crew ingress packet."""
    from gamstcrew import EventPacket

    item = message.get("input")
    if not isinstance(item, dict):
        raise ValueError("input message requires an object")
    input_id = item.get("id")
    capture = item.get("at_ms")
    modality = item.get("modality")
    payload = item.get("payload")
    if not isinstance(input_id, str) or not input_id:
        raise ValueError("input.id is required")
    if type(capture) is not int or capture < 0:
        raise ValueError("input.at_ms must be a nonnegative integer")
    if modality != "video" or not isinstance(payload, dict):
        raise ValueError("geometry runtime accepts structured video inputs only")
    now = time.monotonic_ns() // 1_000_000
    return EventPacket(
        event_id=f"bench-input:{input_id}", stream_id=source_id,
        subject_id=subject_id, modality=modality, event_type="bench.input",
        source_clock="bench_elapsed", capture_timestamp_ms=capture,
        receive_timestamp_ms=now, processing_start_ms=None,
        processing_end_ms=None, start_ms=capture, end_ms=capture,
        sequence=sequence, gap=False, revision=0,
        provider="gamst-bench.input", model_revision="contract-v1",
        value=payload, evidence_ids=(input_id,),
        source_spans=({"input_id": input_id, "capture_timestamp_ms": capture},),
        monotonic_capture_ms=None, clock_id="bench-source",
        clock_epoch="bench-session",
    )


class _CoreBridge:
    """RuntimeManager adapter that owns one CoreProviderRuntime."""

    def __init__(self, runtime, *, source_id: str, sensor_id: str,
                 subject_id: str, input_frame: str, calibration_id: str):
        self.runtime = runtime
        self.source_id = source_id
        self.sensor_id = sensor_id
        self.subject_id = subject_id
        self.input_frame = input_frame
        self.calibration_id = calibration_id
        self.results: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)
        self.sequence = -1
        self.epoch = uuid.uuid4().hex
        self.previous_sequence = None
        self.dropped = 0

    async def start(self):
        await self.runtime.start()

    async def stop(self):
        await self.runtime.stop()

    async def submit(self, packet):
        from gamst import SensorMetadata
        from gamst.plugins import InputFrame

        if not hasattr(packet, "value"):
            raise ValueError("Crew bridge requires EventPacket input")
        sequence = packet.sequence
        gap = self.previous_sequence is not None and sequence != self.previous_sequence + 1
        self.previous_sequence = sequence
        sensor = SensorMetadata(
            self.source_id, self.sensor_id, sequence,
            coordinate_frame=self.input_frame,
            calibration_id=self.calibration_id,
            stream_epoch=self.epoch,
            capture_sequence=sequence,
            clock_id=self.runtime.clock_id,
            clock_epoch=self.runtime.clock_epoch,
        )
        frame = InputFrame(packet.value, packet.modality, packet.capture_timestamp_ms,
                           subject_id=self.subject_id, sensor=sensor)
        started = time.monotonic_ns() // 1_000_000
        try:
            observation = await self.runtime.process(frame)
            ended = time.monotonic_ns() // 1_000_000
            if self.results.full():
                self.results.get_nowait()
                self.results.task_done()
                self.dropped += 1
            await self.results.put({
                "input": packet, "observation": observation,
                "processing_start_ms": started, "processing_end_ms": ended,
                "gap": gap,
            })
        except Exception:
            raise

    def health(self):
        value = dict(self.runtime.health())
        value.update({"dropped": self.dropped, "queue_depth": self.results.qsize()})
        return value


class Adapter:
    def __init__(self):
        self.manager = None
        self.bridge = None
        self.system: dict[str, Any] = {}
        self.query_cutoff: int | None = None
        self.inputs: dict[str, dict[str, Any]] = {}
        self.last_result: dict[str, Any] | None = None
        self.outputs: list[dict[str, Any]] = []
        self.sequence = 0
        self.source_id = "camera"
        self.sensor_id = "structured-points"
        self.subject_id = "local-user"
        self.phase = "startup"
        self.started = False
        self.ended = False

    def child_summary(self):
        """Return bounded parent/child lifecycle state for failure traces."""
        if self.manager is None or self.bridge is None:
            return {"parent": None, "child": None}
        name = next(iter(self.manager.runtimes), None)
        parent = None
        if name is not None:
            health = self.manager.health(name)
            parent = {
                "runtime": health.runtime, "state": health.state,
                "queue_depth": health.queue_depth, "capacity": health.capacity,
                "dropped": health.dropped, "errors": list(health.errors),
            }
        return {"parent": parent, "child": self.bridge.health()}

    def failure_category(self, exc: Exception) -> str:
        """Classify failures from retained parent/child lifecycle state."""
        if self.phase == "startup":
            return "startup_failure"
        if self.phase == "input":
            summary = self.child_summary()
            child = summary.get("child") or {}
            parent = summary.get("parent") or {}
            if child.get("running") is False or parent.get("state") == "crashed":
                return "child_crash"
            if parent.get("errors"):
                return "provider_protocol_failure"
            if isinstance(exc, asyncio.TimeoutError) or str(exc) == "provider timeout":
                return "provider_timeout"
        return "protocol_failure"

    async def emit(self, item: dict[str, Any]):
        print(json.dumps(item, ensure_ascii=False, separators=(",", ":")), flush=True)

    async def start(self, message: dict[str, Any]):
        self.phase = "startup"
        if self.started or self.manager is not None:
            raise RuntimeError("duplicate start")
        configuration = message.get("configuration")
        if not isinstance(configuration, dict):
            raise ValueError("start.configuration is required")
        _add_import_roots(configuration)
        from gamst import ProcessProvider
        from gamstcrew import CoreProviderRuntime, RuntimeDescriptor, RuntimeManager

        provider_config, python, profile, name = _runtime_configuration(configuration)
        self.system = configuration
        self.subject_id = configuration.get("subject_id", "local-user")
        if not isinstance(self.subject_id, str) or not self.subject_id:
            raise ValueError("subject_id must be a non-empty string")
        self.source_id = provider_config.get("source_id", self.source_id)
        self.sensor_id = provider_config.get("sensor_id", self.sensor_id)
        if not isinstance(self.source_id, str) or not isinstance(self.sensor_id, str):
            raise ValueError("provider source and sensor IDs are required")
        spec = ProcessProvider.capability(profile, provider_config)
        self.bridge = _CoreBridge(
            CoreProviderRuntime(python, profile, provider_config),
            source_id=self.source_id, sensor_id=self.sensor_id,
            subject_id=self.subject_id,
            input_frame=provider_config.get("input_frame", "camera.image"),
            calibration_id=provider_config.get("id", "runtime-calibration"),
        )
        descriptor = RuntimeDescriptor(
            name=name, profile=profile, provider=spec.provider,
            model_revision=spec.version, license=spec.license, ready=True,
        )
        self.manager = RuntimeManager(capacity=8)
        await self.manager.register(name, self.bridge, descriptor)
        health = self.manager.health(name)
        await self.emit({"type": "meta", "runtime_contract": "runtime_contract_execution",
                         "quality_claims": False, "host_acceptance": False,
                         "runtime": name, "profile": profile,
                         "provider": spec.provider, "model_revision": spec.version,
                         "license": spec.license, "ready": health.state == "ready",
                         "health": self.bridge.health(),
                         "provenance": message.get("provenance")})
        self.started = True

    async def input(self, message: dict[str, Any]):
        self.phase = "input"
        if self.manager is None or self.bridge is None:
            raise RuntimeError("adapter is not started")
        item = message.get("input")
        if not isinstance(item, dict):
            raise ValueError("input message requires an object")
        input_id = item.get("id")
        if isinstance(input_id, str) and input_id in self.inputs:
            raise ValueError("duplicate input.id")
        self.sequence += 1
        packet = _input_packet(message, sequence=self.sequence,
                               subject_id=self.subject_id,
                               source_id=self.source_id, sensor_id=self.sensor_id)
        self.inputs[input_id] = item
        runtime_name = next(iter(self.manager.runtimes))
        before = self.manager.health(runtime_name).dropped
        await self.manager.submit(runtime_name, packet)
        try:
            result = await asyncio.wait_for(self.bridge.results.get(), timeout=10)
            self.bridge.results.task_done()
        except asyncio.TimeoutError as exc:
            health = self.bridge.health()
            raise RuntimeError("provider timeout") from exc
        after = self.manager.health(runtime_name).dropped
        if after > before:
            await self.emit({"type": "error", "text": "runtime queue dropped input",
                             "failure_category": "queue_drop", "input_id": input_id})
            return
        self.last_result = result
        await self._emit_context(result)

    async def _emit_context(self, result: dict[str, Any], *, query_cutoff: int | None = None):
        from gamstcrew import EventPacket

        packet = result["input"]
        observation = result["observation"]
        capture = packet.capture_timestamp_ms
        event_id = f"core:{packet.event_id}"
        output = EventPacket(
            event_id=event_id, stream_id=self.source_id,
            subject_id=self.subject_id, modality=packet.modality,
            event_type="geometry.plane_points",
            source_clock="bench_elapsed", capture_timestamp_ms=capture,
            receive_timestamp_ms=packet.receive_timestamp_ms,
            processing_start_ms=result["processing_start_ms"],
            processing_end_ms=result["processing_end_ms"],
            start_ms=capture, end_ms=capture, sequence=packet.sequence,
            gap=result["gap"], revision=0,
            provider=self.bridge.runtime.spec.provider,
            model_revision=self.bridge.runtime.spec.version,
            value=observation, uncertainty=None,
            evidence_ids=packet.evidence_ids,
            source_spans=packet.source_spans,
            query_cutoff_ms=(query_cutoff
                             if query_cutoff is not None and capture <= query_cutoff
                             else None),
            monotonic_capture_ms=None,
            clock_id=self.bridge.runtime.clock_id,
            clock_epoch=self.bridge.runtime.clock_epoch,
        )
        refs = list(packet.evidence_ids)
        await self.emit({"type": "context", "text": json.dumps(observation, ensure_ascii=False),
                         "evidence_ids": refs, "packet": output.to_dict(),
                         "runtime_contract": "runtime_contract_execution"})

    async def query(self, message: dict[str, Any]):
        self.phase = "query"
        if not self.started or self.manager is None or self.bridge is None:
            raise RuntimeError("query received before start")
        query = message.get("query")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        self.query_cutoff = message.get("query_ms")
        if type(self.query_cutoff) is not int or self.query_cutoff < 0:
            raise ValueError("query_ms must be a nonnegative integer")
        refs = [input_id for input_id, item in self.inputs.items()
                if self.query_cutoff is None or item.get("at_ms", 0) <= self.query_cutoff]
        if self.last_result is not None:
            # Re-emit the already observed context with the internal watermark
            # after the collector reveals the query. This does not change the
            # query text or erase any observation from the live runtime.
            await self._emit_context(self.last_result, query_cutoff=self.query_cutoff)
        await self.emit({"type": "answer", "text": "Core provider context available for query: " + query,
                         "evidence_ids": refs, "runtime_contract": "runtime_contract_execution"})

    async def end(self):
        self.phase = "shutdown"
        if not self.started or self.manager is None:
            raise RuntimeError("end received before start")
        if self.ended:
            raise RuntimeError("duplicate end")
        self.ended = True
        runtime_name = next(iter(self.manager.runtimes), None)
        health = None if runtime_name is None else self.manager.health(runtime_name)
        await self.emit({"type": "resource", "queue_depth": 0 if health is None else health.queue_depth,
                         "dropped": 0 if health is None else health.dropped,
                         "provider_health": None if self.bridge is None else self.bridge.health(),
                         "scope": "Crew runtime adapter; host/device values unavailable"})
        if runtime_name is not None:
            await self.manager.close(runtime_name)
        await self.emit({"type": "meta", "lifecycle": "stopped",
                         "ready": False,
                         "provider_health": None if self.bridge is None else self.bridge.health(),
                         "runtime_contract": "runtime_contract_execution"})


async def run():
    adapter = Adapter()
    try:
        max_line = 6 * 1024 * 1024
        while True:
            line = await asyncio.to_thread(sys.stdin.buffer.readline, max_line + 1)
            if not line:
                break
            if len(line) > max_line or not line.endswith(b"\n"):
                raise ValueError("bounded newline required")
            message = json.loads(line)
            kind = message.get("type") if isinstance(message, dict) else None
            if kind == "start":
                await adapter.start(message)
            elif kind == "input":
                await adapter.input(message)
            elif kind == "query":
                await adapter.query(message)
            elif kind == "end":
                await adapter.end()
                return
            else:
                raise ValueError("unsupported adapter message")
        if adapter.started and not adapter.ended:
            raise ValueError("adapter input ended before end")
    except Exception as exc:
        category = adapter.failure_category(exc)
        await adapter.emit({"type": "error", "text": str(exc),
                            "failure_category": category,
                            "child_summary": adapter.child_summary(),
                            "traceback": traceback.format_exc(limit=4)})
        if adapter.manager is not None:
            for name in list(adapter.manager.runtimes):
                await adapter.manager.close(name)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(run())


if __name__ == "__main__":
    main()
