# GamstCrew Core-to-bench runtime adapter

This document freezes the design for the real runtime execution slice of
GAMST #331 and Gamst-bench #1. It is written before implementation so that
the adapter remains a narrow execution seam rather than a second perception
or evaluation framework.

The adapter is a JSONL process selected by the frozen bench command map. The
collector still owns the `start → input → query → end` schedule, output
validation, packet checksum verification, trace provenance and process-tree
cleanup. The adapter owns the Crew lifecycle and translates one explicit Core
provider observation into the bench packet contract.

```text
gamst-bench collector
    │ JSONL start/input/query/end
    ▼
Crew runtime adapter (owned subprocess)
    │ RuntimeManager registration and health
    ▼
GamstCrew CoreProviderRuntime
    │ isolated ProcessProvider child
    ▼
GAMST Core provider
    │ observation with capture/clock/evidence metadata
    ▼
Crew adapter EventPacket → JSONL packet-bearing output
    ▼
collector checksum/provenance/temporal trace
```

This path is execution-contract evidence only. It cannot close model quality,
default selection, host acceptance, cost coverage or production readiness.
The dependency-free projective geometry provider is an acceptable first
provider for this seam because it is a real GAMST Core provider and preserves
the complete temporal contract; its synthetic point values are not perception
quality evidence.

## Frozen lifecycle

The adapter must perform the following sequence for each collector task:

1. Parse and validate the `start.configuration` runtime profile. It contains
   the provider profile, exact provider/model/license metadata, selected Python
   executable and provider configuration. No package installation, model
   download or implicit fallback is allowed.
2. Construct a `CoreProviderRuntime` with the selected Python executable and
   profile. Register a thin adapter around it with `RuntimeManager` before any
   input is accepted. The thin adapter delegates `start`/`stop`, exposes
   `health`, and translates a typed `EventPacket` to a Core `InputFrame`.
3. Wait for Crew registration/readiness. Emit a bounded `meta` output with
   runtime name, profile, provider/model revision, Crew readiness and the
   provider `clock_id`/`clock_epoch`. The collector must receive this output
   before the first packet-bearing output.
4. For each `input`, validate the declared capture timestamp, sequence and
   source metadata, build an owned Core `InputFrame`, and submit it through the
   registered Crew runtime. The adapter must not call a second provider path
   directly or bypass the manager for normal input dispatch.
5. On `query`, record the collector's query watermark for diagnostics and
   answer context assembly. This watermark is an internal evidence-causality
   invariant; it never truncates, rewrites or removes the user's query.
6. On `end`, drain accepted work, emit final health/resource diagnostics, stop
   the manager-owned runtime and exit cleanly. A child failure, timeout or
   restart is reported as an `error`/`meta` diagnostic and never converted to
   a successful answer.

The adapter must use bounded queues and preserve the collector's input-drop
semantics. A dropped input is recorded with its input ID and is not silently
replayed by a later restart.

## InputFrame mapping

The first execution profile is `geometry.ground_plane`, which consumes
structured points and does not require raw image bytes. A task input is mapped
as follows:

| Bench field | Core field | Required rule |
|---|---|---|
| `input.id` | `SensorMetadata.capture_sequence` / evidence ID | Stable, unique within the task; never synthesized after dispatch |
| `input.at_ms` | `InputFrame.timestamp_ms` and capture interval | Preserve exactly as the source capture time |
| `input.modality` | `InputFrame.modality` | Must be `video` for this profile |
| `input.payload` | `InputFrame.data` | Exact bounded `{reference_id,image_size,points}` object; no raw media or annotations |
| `source_id`/`sensor_id` | `SensorMetadata.source_id`/`sensor_id` | Must match frozen provider configuration |
| declared input frame/calibration | `SensorMetadata.coordinate_frame`/`calibration_id` | Must match the provider profile exactly |
| stream epoch | `SensorMetadata.stream_epoch` | Assigned once per Crew provider lane and changes on reset/restart |
| provider clock | `SensorMetadata.clock_id`/`clock_epoch` | Take from the live `CoreProviderRuntime`; never invent or copy wall time |
| input sequence | `SensorMetadata.sequence` | Strictly increasing accepted sequence; gaps are explicit |

The bridge may retain the last provider observation only until it has emitted a
packet for that input. It must not retain raw pixels or add future task
annotations to Core context.

## Temporal packet mapping

The Core observation is wrapped in the shared `EventPacket` contract before it
is written to adapter stdout. The mapping is:

| EventPacket field | Source and rule |
|---|---|
| `event_id` | Stable adapter event ID derived from the accepted input and provider output; unique per revision |
| `stream_id` / `subject_id` | Frozen source/subject identifiers from the task configuration |
| `modality` / `event_type` | Core capability metadata (`video`, `geometry.plane_points`) |
| `source_clock` | `monotonic` (or the explicit Core source clock) |
| `capture_timestamp_ms` | Original `InputFrame.timestamp_ms` |
| `receive_timestamp_ms` | Adapter receive time, measured locally and never copied from provider output |
| `processing_start_ms` / `processing_end_ms` | Adapter/Crew monotonic processing interval when available; otherwise `null`, never guessed |
| `start_ms` / `end_ms` | Core observation interval; a frame event uses the capture timestamp for both bounds |
| `sequence` / `gap` | Accepted input sequence and explicit queue/restart gap state |
| `revision` / `supersedes` | Core revision lineage; first observation is revision `0`, later corrections reference the superseded event |
| `provider` / `model_revision` | Frozen provider descriptor and exact model/provider revision from the live spec |
| `value` / `uncertainty` | Bounded Core observation and its declared uncertainty; uncalibrated geometry remains an estimate |
| `freshness_ms` | Frozen profile freshness bound |
| `evidence_ids` / `source_spans` | Input ID and Core evidence lineage only; no hidden annotation IDs |
| `query_cutoff_ms` | Internal watermark attached only when the packet is used for query support; a packet captured after it is rejected for that use |
| `clock_id` / `clock_epoch` | Exact live provider clock identity and worker epoch; a restart creates a new epoch |
| `checksum` | `EventPacket.to_dict()` canonical SHA-256 envelope, verified by the bench collector before dispatch |

The checksum covers the canonical packet body and is not copied into the
observation value or evidence IDs. The adapter must emit the complete packet,
not a checksum-less legacy packet, for measured runs.

## Output and diagnostics

The adapter may emit only bounded JSONL messages accepted by the collector:

- `meta`: immutable runtime identity, readiness, clock epochs, restart count,
  exact source commits and adapter contract version.
- `context`: human-readable bounded context plus `evidence_ids`; its optional
  `packet` is the canonical Core-derived `EventPacket`.
- `resource`: Crew health, queue depth, drops, provider latency and adapter RSS
  with an explicit measurement scope. Unknown host/device values remain `null`.
- `error`: typed startup, protocol, provider or shutdown failure with bounded
  diagnostics. Errors remain failures in the trace.

The collector adds its own receive timestamp and verifies packet checksums. The
adapter must not claim model-server VRAM, energy, invoices or remote-server
latency without a separate instrumented scope.

## Provenance and acceptance boundary

Measured runs require a frozen runtime manifest containing exact `gamst`,
`gamstcrew` and `gamst-bench` commits, dependency lock, provider/model
revision, license/artifact identity, host profile, adapter command digest and
context-contract revision. The collector retains this map in `start`, trace
provenance and packet-bearing diagnostics.

The following are required for #331/#1 runtime execution evidence:

- a real Core provider packet crosses the live Crew-owned process boundary;
- readiness/health is observed before dispatch and shutdown/restart outcomes
  are visible;
- capture time, receive/process timing, source clock, worker epoch, sequence,
  revision, evidence lineage and checksum survive the crossing;
- drops and errors are counted, bounded and preserved in the trace; and
- the run is reproducible from its frozen manifest and exact command map.

The following remain separate open gates and must be reported as such:

- trained-model quality, grounded answer quality and cross-modal superiority;
- Mac/Linux/CUDA/Windows/Jetson host acceptance;
- matched held-out B/C/D/E measurements, CostBench and default promotion;
- complete model-server/device resource and cost accounting; and
- required independent review and merge approval.

No synthetic fixture, checksum probe or dependency-free geometry execution may
close those gates. The adapter's first run is labelled
`runtime_contract_execution`, with `quality_claims: false` and
`host_acceptance: false` in its report metadata.
