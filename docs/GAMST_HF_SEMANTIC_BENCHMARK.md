# GAMST High-Frequency Semantic Benchmark

**Status:** protocol design; no measured score yet.

This benchmark targets a gap in ordinary video QA: a low-frequency snapshot must
not solve the task. The answer requires continuous, high-frequency observation
and semantic episode tracking. It evaluates the approved architecture:

```text
camera ───────────────→ small StreamingVLM → video semantic state
  ├→ lightweight video modality models ─┐
  ├→ microphone → audio models ─────────┤→ GAMST signals
  └→ physical sensors → physical models ┘
                              ↓
                 Semantic State Fusion → Semantic State Chain
                              ↓
                         MCP Context → Strong VLM + LLM
```

A learned decision model is not a strong-model trigger in this protocol. Any
strong-model trigger is a frozen application rule. `decision.multimodal`, if
used, is an ordinary perception signal and is ablated separately.

## Why existing benchmarks are insufficient

FastBench, OmniPro and StreamArena are useful external tracks, but they do not
isolate all of the following in one controlled experiment:

- high-frequency-only visual evidence;
- stateful video semantics separate from specialist signals;
- fusion of video state with audio/physical observations;
- correction of an earlier state after new evidence;
- strong-model token/cost accounting at equal semantic quality.

Their scores must remain separate from this benchmark.

## Dataset unit

The unit is a complete synchronized episode, never an isolated frame. Each
session contains:

- video at a declared capture rate (30–120 FPS source);
- audio at 16 kHz or a declared sensor rate;
- optional IMU/contact/rotation/force lanes;
- timestamped user questions and event deadlines;
- frame/audio/sensor evidence IDs;
- state, event-order, relation, revision and answer annotations.

Each episode has a **high-frequency-only gate**. An answer is not scorable from
the keyframe set alone. Annotation authors must mark the minimum temporal
interval and minimum effective sample rate required to answer.

## Anti-shortcut construction

Every task has paired controls:

1. full high-frequency stream;
2. 1 FPS or keyframe-only stream;
3. shuffled-frame stream;
4. event-order-preserving but appearance-masked stream where applicable;
5. modality ablation streams (video-only/audio-only/physical-only).

A task is admitted only if:

- a human or reference model fails the 1 FPS/keyframe control at the preregistered threshold;
- shuffling the required interval reduces score;
- the answer depends on at least two distinct temporal observations;
- future frames after the query cutoff cannot reveal the answer;
- annotations specify the earliest supporting evidence and the latest acceptable answer time.

Repeated views of a static final frame are not a valid high-frequency task.

## Task suites

### HF-1: Fast state transition

Examples: hand releases a cup, ball changes direction, vehicle brakes, object enters
a restricted region. The final frame alone is ambiguous or identical across labels.

Measure: transition recall, detection latency, false alerts/hour.

### HF-2: Multi-step episode order

Examples: pick up → carry → place; pitch → swing → impact → result; tool grasp →
operation → completion. The answer requires the ordered chain, not a final caption.

Measure: event-order accuracy, missing-step rate, causal-relation accuracy.

### HF-3: Audio-visual synchronization

Examples: two visually similar impacts where only audio distinguishes them; a
horn/voice/alarms aligned to a visual state; audio preceding or following a motion.

Measure: cross-modal accuracy, AV offset tolerance, contradiction rate, modality
ablation delta.

### HF-4: Streaming state and last-seen memory

Examples: an object is visible, occluded, moved, and later queried; a score/status
changes and the user asks for current versus last-seen value.

Measure: current-state accuracy, last-seen accuracy, state freshness, stale-state rate.

### HF-5: Revision and correction

Examples: early view suggests cup, later view proves bottle; early audio suggests
one event, later video corrects it; a tracker identity is corrected after occlusion.

Measure: correction accuracy, correction latency, stale-claim rate, evidence lineage.

### HF-6: Physical dynamics

Examples: coin rotations, wheel RPM, contact/impact, acceleration, trajectory,
fall-and-stop. The answer requires a continuous signal, not a single image.

Measure: count/RPM error, transition latency, sensor-video consistency, dropout recovery.

### HF-7: High-frequency overload and recovery

Inject bounded frame/audio gaps, delayed ASR, plugin restart and queue pressure.
The agent must not promote stale state to current state.

Measure: recovery time, dropped-input accounting, stale-state errors, false alerts.

## Frozen arms

| Arm | Pipeline |
| --- | --- |
| A | Strong VLM receives the declared native high-frequency evidence window at every fixed semantic interval. |
| B | Lightweight modality models + state chain + LLM; no StreamingVLM semantic state. |
| C | Lightweight modality models + pinned StreamingVLM video state + GAMST fusion/state chain + application-owned strong VLM/LLM context. |
| D | Same inputs and strong model as C, but no persistent semantic state chain (window-only control). |
| E | StreamingVLM video state only, without specialist audio/physical signals. |
| F | Optional rules-based `decision.multimodal` signal added to C; it is a perception ablation, not a trigger authority. |

All arms freeze source rates, plugin revisions, StreamingVLM checkpoint, strong
VLM checkpoint, LLM consumer, prompts, context limits, hardware, warm state and
failure policy. C and D differ only in the semantic state chain. C and E differ
only in specialist modality fusion.

## Primary metrics

- grounded semantic answer success;
- event/episode correctness;
- p95 answer-ready latency;
- strong VLM calls and prompt tokens;
- total pipeline cost;
- stale-state error rate;
- revision correctness;
- high-frequency update latency;
- dropped inputs and recovery time.

A GAMST claim requires equal or preregistered-tolerance grounded quality versus A,
lower strong-model calls/tokens/cost, no material stale-state increase, and
stable realtime updates. Frame count is not sample size; confidence intervals
are session-clustered.

## Required evidence artifacts

Each run stores:

- frozen plugin/model/runtime manifest;
- source rates and actual accepted/dropped input counts;
- semantic state-chain JSONL;
- evidence IDs and query cutoffs;
- strong-model usage receipts;
- raw scorer output;
- ablation/control results;
- provenance and checksum for every published summary.

No result is called SOTA or superior until the full high-frequency gates and
held-out session-cluster acceptance are passed.
