# GAMST native benchmark extensions

**Evidence class: code + unit tests only.** No result in this document is a measured benchmark result. These tracks are named `gamst-extension`; they modify the model front-end and must never be uploaded or relabelled as official-protocol scores. Dataset preprocessing, timed event delivery, native output parsing, and native scorers remain the pinned upstream implementations.

## Pinned interfaces inspected

The read-only checkouts used for this inspection were `/tmp/upstream/{fastbench,omnipro,streamarena}`.

### FastBench

Revision `1951dd11b7423cd76998c9f2fb04e71e95a232b1` (`Ashone3/FastBench`).

- `scripts/eval_qwen3_vl_8b_proactive_frame.sh:136-172` invokes `run_stream_eval_parallel.py` with model `qwen3_vl`, the dedicated YAML, 2 FPS, `--proactive-focus`, a 90-frame focus budget, and the native scorer. `configs/proactive_frame.yaml:1-88` defines `Silent`, `Focus_Start`, `Focus_End`, and the timed-answer prompt.
- `run_stream_eval.py:740-759` is the OpenAI-compatible model wrapper. Its `generate(messages, max_new_tokens, ...) -> {response, raw_response, status_code}` implementation is at `run_stream_eval.py:1248-1326`; `build_backend` is the replaceable factory at `run_stream_eval.py:1508-1516`.
- `SessionModel.new_session`, `add_chunk`, and `generate` are at `run_stream_eval.py:1520-1562` and `run_stream_eval.py:1882-1883`. The default causal chunk loop at `run_stream_eval.py:4076-4125` appends one timestamped video chunk and any newly disclosed questions, calls the backend, records focus actions, and returns native `responses`.
- `run_stream_eval_parallel.py:54-81` keeps one `UnifiedInferenceRunner` per worker and `run_stream_eval_parallel.py:116-151` writes the unchanged native sample records.

**Extension seam:** `gamst_bench.extensions.fastbench_agent.GamstFastBenchBackend` implements the backend result contract. Its `install()` patches only the in-memory `build_backend`; the checkout remains unchanged. The module invokes `run_stream_eval_parallel.main()`, including the native scorer. A `gamst` YAML backend or `GAMST_EXTENSION_FASTBENCH_MODEL=qwen3_vl` selects the extension.

### OmniPro

Revision `7c72e8117f180bf9a22320c1dc2c005bbe4c4a0f` (`RuixiangZhao/OmniPro`).

- `scripts/run_online.py:35-69` defines the native CLI; `build_model` at `scripts/run_online.py:72-134` constructs an online model, and `gpu_worker` at `scripts/run_online.py:163-177` passes it to `OnlineEvaluator`.
- `models/streaming_base.py:37-91` is the required model interface: `begin(instruction, task_meta)`, `observe(frame, t_sec, history, audio_chunk=None) -> Optional[str]`, and `end()`. The frame is HWC uint8, audio is optional 16 kHz mono, `None`/empty means STANDBY, and a nonempty string is a native emit.
- `evaluators/online_evaluator.py:221-252` reveals each frame/audio chunk in timestamp order and collects nonempty outputs; `evaluators/online_evaluator.py:254-285` writes native `predictions: [{t_sec, raw, parsed?}]`. Task-specific raw output grammar is in `utils/prompts.py:717-840` and `utils/online_parser.py:1-92`.

**Extension seam:** `create_streaming_model_class(StreamingModel)` returns a real subclass, so OmniPro's `isinstance` gate still applies. The launcher preserves the pinned parser and evaluator while adding model name `gamst` (also accepted: `gamst-extension`). No ground truth or future task metadata is sent to the VLM.

### StreamArena / StreamMind

Revision `ec0325b9552b045c2e53afbf425315ce867313ee` (`JIA-Lab-research/StreamArena`).

- `method/streammind/agent.py:42-68` defines `DriverAPI.commit_answer(qid, text)` and `emit_speak(qid, text, video_ts)`. `StreamingAgent` is at `method/streammind/agent.py:72-172`: `start`/`stop` bracket every video; `on_frame(Frame)` receives `frame.ts` and base64 JPEG; `on_audio_observation` receives ASR text; `on_ask` and `on_e_watch` implement final and proactive answers.
- `method/streammind/run_streammind.py:57-72` dynamically loads `package.module:ClassName` and verifies `isinstance(obj, StreamingAgent)`. The causal scheduler is at `method/streammind/run_streammind.py:311-432`; native record synthesis, including `model_answer`, `e_proactive_msgs`, `e_missed`, and latency, is at `method/streammind/run_streammind.py:252-297`.
- `method/streammind/scripts/run_streammind.sh:12-29` exposes `AGENT`, `DATASET`, `VIDEO_DIR`, `OUT`, `FPS`, and `ASR_URL` without changing the driver.

**Extension seam:** `GamstStreamArenaAgent` subclasses the `agent.StreamingAgent` already imported by the native driver. A bounded FIFO preserves accepted-input order; drops are explicit sidecar events. Questions trigger an explicit GAMST query; E-watchers use proactive native `emit_speak` only on a policy-selected VLM response.

## Exact native-runner invocation

Set the two import roots and the matched backbone. `GAMST_EXTENSION_SIDECAR` must be a new per-run JSONL path. All endpoints default to local HTTP; remote media transmission additionally requires `GAMST_EXTENSION_ALLOW_REMOTE=1` and HTTPS.

```bash
export PYTHONPATH=/srv/gamst-bench:/srv/catch-your-mind
export GAMST_EXTENSION_VLM_URL=http://127.0.0.1:8080/v1
export GAMST_EXTENSION_MODEL=Qwen/Qwen3-VL-8B-Instruct
export GAMST_EXTENSION_POLICY=sentinel
export GAMST_EXTENSION_SEMANTIC_INTERVAL_MS=5000
export GAMST_EXTENSION_COOLDOWN_MS=1000
export GAMST_EXTENSION_CHANGE_ENTER=0.08
export GAMST_EXTENSION_CHANGE_EXIT=0.03
export GAMST_EXTENSION_SIDECAR=/srv/runs/REPLACE_RUN/gamst-calls.jsonl
```

FastBench, using the unmodified ProactiveFrame YAML and native parallel runner/scorer:

```bash
GAMST_EXTENSION_FASTBENCH_MODEL=qwen3_vl \
python -m gamst_bench.extensions.fastbench_agent \
  --fastbench-root /srv/benchmarks/fastbench -- \
  --model-name qwen3_vl \
  --config /srv/benchmarks/fastbench/configs/proactive_frame.yaml \
  --video-root /srv/benchmarks/fastbench \
  --output-dir /srv/runs/REPLACE_RUN/fastbench \
  --run-id gamst-extension --num-workers 1 --num-scorers 1 \
  --proactive-focus
```

The thin shim `gamst_bench/extensions/shims/fastbench_gamst.py` may be copied into the FastBench checkout and invoked with the same arguments; it only imports the module above.

OmniPro online inference followed by its native scorer:

```bash
python -m gamst_bench.extensions.omnipro_agent \
  --omnipro-root /srv/benchmarks/omnipro -- \
  --model gamst --data_path /srv/data/omnipro/benchmark.json \
  --num_gpus 1 --output_dir /srv/runs/REPLACE_RUN/omnipro --no_resume
python /srv/benchmarks/omnipro/scripts/compute_online_metrics.py \
  --pred_dir /srv/runs/REPLACE_RUN/omnipro --tolerance 3
```

The thin shim is `gamst_bench/extensions/shims/omnipro_gamst.py`. `model_path` is not used to load a second local model; the OpenAI server's pinned model name is authoritative.

StreamArena continuous/proactive inference:

```bash
AGENT=gamst_bench.extensions.streamarena_agent:GamstStreamArenaAgent \
DATASET=/srv/data/streamarena/question.en.jsonl \
VIDEO_DIR=/srv/data/streamarena/videos \
OUT=/srv/runs/REPLACE_RUN/streamarena/records.jsonl \
FPS=2 ASR_URL=http://127.0.0.1:9001 \
bash /srv/benchmarks/streamarena/method/streammind/scripts/run_streammind.sh
bash /srv/benchmarks/streamarena/judge/scripts/run_judge.sh \
  /srv/runs/REPLACE_RUN/streamarena/records.jsonl
```

## GAMST APIs used and gaps

Used from the `feat/temporal-contract` GAMST checkout:

- `gamst.Gamst(consent=True, ...)` and async lifecycle (`gamst/engine.py:39-85`, `gamst/engine.py:162-168`).
- `CapabilitySpec`, `OutputField`, and `SensorMetadata` to register measured video-change and audio-energy signals (`gamst/capabilities.py:66-180`).
- `Gamst.register_capability` and `Gamst.push_signal` (`gamst/engine.py:267-280`, `gamst/engine.py:327-390`). Every video recommendation is evaluated against the returned real `observation.signal` record.
- `gamst.call_policy.CallPolicy.recommend` (`gamst/call_policy.py:25-130`), including measured thumbnail change, hysteresis, cooldown, freshness, periodic blindspot audits, explicit queries, and exact visual-evidence SHA256 binding. `CallPolicy` recommends; the adapter alone dispatches and records actual calls.
- `Gamst.build_temporal_context(query_cutoff_ms=...)` (`gamst/engine.py:987-1053`) for bounded, cutoff-filtered evidence and revisions. VLM text and ASR text are retained as timestamped text signals with their original provider provenance.

Gaps / deliberate substitutions:

1. `FreshFrameSentinel.open` requires a registered GAMST call controller and starts `SmolVLMCalls.open` (`gamst/frame_sentinel.py:35-100`). It cannot directly front the matched remote Qwen3-VL OpenAI backbone. The extensions therefore use `CallPolicy` + `Gamst` directly rather than silently running a different sentinel model.
2. `CallPolicy` is imported from `gamst.call_policy`; it is not re-exported by `gamst/__init__.py`.
3. Qwen3-VL-8B has no PCM-audio chat input. OmniPro PCM is still consumed causally and retained as RMS energy, but no transcription or audio-semantic claim is fabricated. A matched audio-capable A/C/D backbone is required for audio-semantic benchmark claims.
4. FastBench emits one native response per chunk. If several frames in one chunk are selected, every VLM call is logged, while the last non-`Silent` native response occupies that chunk's single native slot.
5. The code tests use fake OpenAI/Live sessions and tiny synthetic images solely as software fixtures. They are not quality, latency, or cost measurements.

## Sidecar JSONL

Each native adapter writes `session_start`, `selection`, `vlm_call`, `native_emit`, and `session_summary` records (plus audio/drop/error records when applicable). Every record declares `evidence_class` (`smoke` by default, `synthetic` for fixtures, or `measured` only for a real measured run via `GAMST_EXTENSION_EVIDENCE_CLASS`). `vlm_call` contains actual call index, evidence IDs, start/completion Unix timestamps, token usage returned by the provider, and `time_to_detect_ms` relative to selected evidence capture. The summary contains input, selected, VLM-call, emit, drop, and error counts. Media bytes, prompts, API tokens, and model weights are not written to the sidecar.

## Commercial lane

`gamst_http.request_chat(..., key_env=...)` now accepts base `/v1` URLs and complete Vertex/Gemini `/chat/completions` URLs. Remote HTTPS requires `--allow-remote`. `--vlm-key-env` / `--consumer-key-env` (or `GAMST_BENCH_VLM_KEY_ENV` / `GAMST_BENCH_CONSUMER_KEY_ENV`) contain **names of environment variables**, not tokens. Role-specific credentials suppress the legacy `GAMST_BENCH_API_KEY` fallback; secrets never belong in commands or run artifacts.

Arm F is `python -m gamst_bench.adapters.gemini_live`. It lazily uses optional `google-genai`, one persistent Live session per task, capture-time 1 FPS JPEG, mono PCM16LE realtime audio, native `answer`/`usage`/`meta` JSONL, and strict `query_ms` evidence filtering. `GOOGLE_API_KEY` or `GEMINI_API_KEY` supplies the credential. Tests inject fake sessions; no real commercial call has been made.
