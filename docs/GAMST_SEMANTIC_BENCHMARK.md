# GAMST Semantic Streaming Benchmark — protocol draft

**Status:** protocol draft; no score exists yet.

## Goal

Measure GAMST's actual claim: high-frequency, low-cost perception and semantic state updates provide a continuously useful multimodal context to a consumer LLM/VLM without running a strong VLM on every frame.

This is not a replacement for FastBench, OmniPro or StreamArena. Those remain external tracks. This benchmark evaluates the GAMST architecture itself.

## Input tracks

Every session has synchronized, timestamped lanes:

- video: frames plus a short evidence ring buffer;
- audio: PCM, VAD and optional ASR transcript;
- text: user questions and system events;
- physical: IMU/contact/rotation/environment events where the scenario provides them.

The held-out unit is a complete session, not a frame. Questions and annotations are disclosed only at their registered time.

## Frozen configurations

| Arm | Definition |
| --- | --- |
| A | Strong VLM receives the native evidence window at every declared semantic interval. |
| B | Perception plugins + consumer LLM; no semantic VLM. Diagnostic cost lower bound. |
| C | Explicit perception plugin recipe + GAMST semantic state chain + application-owned context request. Strong VLM only when the application rule requests it. |
| D | Same perception recipe and strong VLM, fixed periodic semantic update. Tests whether the state chain is better than a schedule. |
| E | Small streaming semantic model updates state continuously; strong VLM is disabled. |

Each arm pins plugin factories, model revisions, asset hashes, cadence, ring-buffer window, state-chain limits, prompt, consumer revision, hardware, warm state and failure policy. No arm may silently replace a missing plugin with a thumbnail-only trigger.

## Required scenario suites

1. **Transient event:** brief event must be detected before evidence expires.
2. **Semantic flow:** multi-step episode where order and causality matter.
3. **Audio-video fusion:** the same event requires synchronized visual and acoustic evidence.
4. **State retention:** answer requires current state plus last-seen state.
5. **Revision:** audio/video or sensor evidence corrects an earlier semantic state.
6. **Physical state:** rotation, contact, acceleration or spatial state must be tracked.
7. **Overload/recovery:** dropped input, plugin restart and stale evidence must not create a false current state.

## Context contract

The consumer receives only a cutoff-filtered packet containing:

- semantic state-chain updates;
- structured events and relations;
- evidence IDs and capture times;
- source modality and model provenance;
- freshness and input watermark;
- selected evidence frames/audio windows when the frozen application rule requests them.

The packet must not claim that a frame was understood when only a scalar perception signal exists. Raw media remains outside normalized memory and is included only through explicit evidence references.

## Metrics

Primary:

- grounded answer success;
- answer-ready latency relative to the scenario deadline;
- semantic-flow correctness;
- current/last-seen state correctness.

Secondary:

- strong VLM calls and prompt tokens;
- semantic-update calls/tokens;
- plugin CPU/GPU time;
- full-pipeline cost;
- stale-state errors;
- unsupported claims;
- revision correctness;
- false alerts/hour;
- dropped inputs and recovery time;
- memory bytes and packet truncation.

A quality claim requires paired session-level bootstrap intervals. Frame count is not sample size. Synthetic fixtures are engineering tests only and cannot pass acceptance.

## Required ablations

- native evidence vs selected evidence window;
- state chain disabled vs enabled;
- video-only vs video+audio;
- rules-only application routing vs learned multimodal decision plugin;
- strong VLM every interval vs C application-owned escalation;
- semantic model disabled vs small streaming semantic model.

The learned decision plugin is an optional perception signal in this protocol. It is not the authority that invokes a strong model; trigger behavior belongs to the frozen application/MCP orchestration.

## Acceptance gate

Do not claim GAMST superiority until a held-out campaign shows, at minimum:

- no loss of grounded success beyond the preregistered tolerance;
- lower whole-pipeline cost and strong-VLM token use;
- no material increase in p95 answer latency;
- no increase in stale/unsupported claims;
- all modality lanes and plugin revisions independently reproducible.
