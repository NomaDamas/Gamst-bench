# JSONL adapter contract

## GAMST Core through GamstCrew

The live runtime-manager-to-benchmark execution seam is frozen in
[`GAMSTCREW_RUNTIME_ADAPTER.md`](GAMSTCREW_RUNTIME_ADAPTER.md). It defines the
JSONL lifecycle, the real Crew-owned Core provider boundary, temporal packet and
checksum preservation, failure categories, provenance, and the explicit limits
of the first `runtime_contract_execution` profile. The document is design
evidence only until issue [#9](https://github.com/NomaDamas/Gamst-bench/issues/9)
has a passing implementation and trace artifact.

The collector runs an explicitly supplied argv command, never a shell string. Use an absolute executable path. stdout is reserved for newline-delimited JSON; stderr is diagnostic. No model weights are downloaded by the benchmark.

An adapter output may include a temporal packet in its `packet` member. The
collector verifies its versioned SHA-256 envelope before adding receive-time
metadata or dispatching the output to scoring. The covered bytes are canonical
UTF-8 JSON (`ensure_ascii=false`, sorted keys, compact separators,
`allow_nan=false`) with the `checksum` member excluded. A mismatch rejects the
output and increments `integrity_rejected` in the trace. Packets without a
checksum are rejected; legacy acceptance is an explicit compatibility choice
for direct contract consumers and is not enabled by the collector. Accepted
checksum envelopes are retained in the trace's bounded `packet_checksums`
field so an audit can bind the received packet set to the trace digest.

Input messages, in order:

```json
{"type":"start","schema_version":2,"configuration":{"id":"C","policy":"hybrid"},"consumer_model":"pinned-model","consumer_revision":"pinned-revision"}
{"type":"input","input":{"id":"frame-1","at_ms":100,"modality":"video","payload":{"jpeg_base64":"..."}}}
{"type":"query","query":"What changed?"}
{"type":"end"}
```

`start.configuration` is the full frozen system object. Each input arrives on its recorded wall-clock schedule. Queries are withheld until query time. Input modalities: video JPEG, audio little-endian float32 PCM plus `sample_rate`, text, signal, or control. A plan may reference a local media blob with `{path,sha256,field}` inside `payload`; the collector verifies bytes and materializes the specified base64 field. Individual media blobs are limited to 4 MiB; the reference adapter accepts input lines up to 6 MiB. Large input manifests should use blob paths. Store blobs with the frozen experiment, not inside public source control when private.

Output examples:

```json
{"type":"context","text":"The counter reads 4.","evidence_ids":["frame-1"]}
{"type":"answer","text":"The counter changed to 4.","evidence_ids":["frame-1"]}
{"type":"resource","rss_mb":null,"queue_depth":0,"dropped":0,"age_ms":125}
{"type":"usage","calls":2,"cost_quantities":{"vlm_input":100,"vlm_output":20,"consumer_input":80,"consumer_output":10}}
```

Allowed output types: context, answer, alert, usage, resource, error, meta. Output line cap 64 KiB, text cap 32 KiB, 128 citations, 10,000 output records per task. Usage is cumulative and unverified until accounting review. Resource fields may be null. The host overwrites delivery timestamps. Citing unknown or not-yet-delivered inputs fails the run. Use `answer` only for the first final response; interim context belongs in `context`. Finish after `end`, while allowing in-flight inference to drain within the frozen timeout.

Input ingestion and inference must be independent. The host has an eight-message input queue and logs drops; the reference adapter has bounded video/audio/semantic/consumer queues. Input schedule does not wait for model inference. Startup, decode and task teardown are included in the collected wall-clock run; declare cold/warm conditions. Persistent model-server state must be reset consistently across configurations.

## Reference adapter

`python3 -m gamst_bench.adapters.gamst_http` connects to explicitly selected chat-compatible model endpoints. A uses the VLM; B requires installed Gamst plugins; C adds thumbnail-change, query-triggered semantic calls and periodic auditing; D uses periodic semantic inspection; E (`streaming`) sends frames to a separate small-VLM endpoint (`--streaming-url`, default port 8081) every `--streaming-interval` seconds (default 0.25 s, 4 Hz) without Gamst plugins. C's image-difference trigger is a reference implementation, not a validated semantic sentinel. Audit freshness is anchored to inspected input capture time. Freeze intervals, novelty threshold, plugin configuration, dependencies and adapter source revision.

Non-VLM paths require an existing `gamst` installation (package `gamst-sdk`, class `gamst.Gamst`) and `GAMST_BENCH_PLUGINS`, e.g. a JSON list of `{"factory":"your_module:factory","kwargs":{}}`. Use actual supported factories; the benchmark does not guess or install them. Video plugins require numpy/OpenCV, audio plugins require numpy. Exact checkpoint/plugin compatibility has not been validated by the public synthetic tests.

Default endpoints are local `/v1` chat servers on ports 8080 (VLM) and 11434 (consumer). `--consumer-json-mode` requests OpenAI-compatible `response_format: {"type":"json_object"}` for the structured consumer answer; enable it only when the selected server supports that option. Input `at_ms` values are mapped to a wall-clock capture origin and passed to Core instead of substituting inference time. Remote endpoints require explicit `--allow-remote` and HTTPS. Credentials use `GAMST_BENCH_API_KEY`; redirects and environment proxies are disabled. Decide whether sending the recorded media to that provider is authorized before opting in. Never put tokens into command files or committed artifacts.

The reference VLM-only path rejects raw audio rather than pretending to evaluate it. Supply a matched audio-capable baseline for audio/video experiments. Context source wrappers may include multiple consumed inputs; reviewers still verify which inputs actually support each answer. This adapter does not implement an audio/video alignment model, calibrated probabilities, proactive timing scorer, or complete GPU/host cost instrumentation. Those are experiment-specific components, not inferred measurements.

Collector RSS covers only its owned adapter process tree. Separate model servers, device memory and provider resource use need separate instrumentation. Resources reported by an adapter are explicitly unverified. Soak output is hash-chained for integrity, not authenticated proof of measurement.

For an adapter `error` output, the collector keeps the stable
`diagnostics: ["adapter_error"]` marker and also retains bounded structured
entries in `failure_diagnostics`. Each entry may include the adapter's
`failure_category`, bounded error text/traceback, and parent/child lifecycle
summary. This preserves startup, timeout, protocol, crash, and queue-drop
causes in the trace without treating any failure as a successful run.
Collector-side deadline expiry is recorded as `collector_timeout`; an adapter
that exits nonzero without emitting a structured error is recorded as
`adapter_exit` with its return code. These diagnostics are bounded and remain
separate from semantic quality or cost acceptance.
