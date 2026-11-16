# GAMST context protocol v0.2

## Scope and hypothesis

Gamst supplies existing agents with useful, bounded context. The hypothesis is that a lightweight perception path with selective semantic inference preserves useful evidence while reducing **whole-pipeline** cost and answer-ready latency. This benchmark tests a configuration, not a model in isolation. FastBench, SPOT-Bench and Inf-Streams-Eval remain complementary external evaluations.

A configuration pins sensors, sampling, perception plugins, VLM checkpoint/revision/precision, call policy, memory window, consumer model/prompt, hardware, warm state and resource budget. A is VLM-centered, B thin perception, C hybrid selective, D periodic hybrid, E a small streaming VLM (policy `streaming`) running continuously on its own lightweight checkpoint. A/C/D must use the same VLM; every configuration uses the same consumer and input track. Every configuration declares `role` (`primary` or `sweep`) and `budget_calls` (semantic VLM calls per session). Sweep configurations are hybrid/periodic variants at other budgets; they trace the cost–quality curve and never serve as baseline, candidate or control. Audio-capable and visual-only experiments must be separate. Comparing unequal hardware or sensor availability is not an acceptance comparison. No-context and oracle configurations are optional diagnostic controls.

Measured plans also bind a separately frozen runtime manifest digest. The manifest records the OS/architecture/hardware, Python and dependency lock, provider and model revisions/licenses/artifacts, consumer and prompt revisions, context contract, and capture/query-cutoff timing policy. Collection and scoring require the exact manifest; synthetic plans intentionally omit it.

## Tasks

- `transient`: short visible events, crossings and brief objects; report duration buckets and misses.
- `semantic`: small OCR/status changes versus visually large irrelevant motion. Include negative controls so motion alone cannot win.
- `memory`: current versus last-seen location/state, occlusion, identity switches, absence and unknown.
- `revision`: audio/video conflicts, delayed transcripts and corrections; the newest supported state must supersede prior claims.
- `retention`: questions revealed after the relevant evidence; include distractors and questions about forgotten detail.
- `resilience`: missing sensors, queue overload, pause/resume, deletion and recovery. Deleted context must not reappear.

Each task declares the first evidence availability, query disclosure, answerability, deadline, critical fact IDs, session/participant/source identifiers, and chronological input packets. Freeze annotations before collecting test runs. Never send annotations, future frames or future questions to adapters. A task currently contains one final query; multi-query continuous sessions require separate segmentation and explicit retained-state policy. The collector restarts a process for each configuration/task; use soak for continuous-runtime diagnostics.

## Metrics

**Grounded on-time success** = execution succeeds AND first final answer is correct AND evidence supports it AND no unsupported claims/stale error AND answer arrives within the fixed deadline. Correct abstention counts only for unanswerable tasks. An early answer before query/evidence availability cannot pass. Later revised answers do not replace the first final answer.

Answer latency = first final answer arrival − max(evidence availability, query disclosure). Error, timeout and premature answers receive the frozen timeout penalty. Context latency = first supported context delivery − evidence availability, including context delivered before a later question. Semantic support is externally reviewed; an existing citation alone is not proof.

Also report critical fact recall, unsupported claims / total claims, stale-error task rate, correct abstentions, false alerts / stream hour, full-pipeline USD / stream hour, actual calls, RSS, queue depth, dropped input, evidence age, time-to-detect, recovery and escalation. Collector traces preserve each cited input's capture timestamp and delivery timestamp; answer evidence must be at or before the query cutoff, even when delivered later. Unknown charges stay unknown, never zero. Include capture, thin perception, VLM, consumer, storage/network and host/device allocation in the accounting method. Declare whether rates are reserved or amortized and whether idle capacity is included. The generic token adapter alone does not provide complete accounting.

## Statistical contract and acceptance

Pre-register plans, data split, rubric, deadlines, command/configuration hashes, failure policy, minimum independent sessions and bootstrap seed before running held-out data. Split at session level, with participant and source separation across development/test. The validator detects overlap within a supplied plan; reviewers must check across releases and external development data.

Run all task/configuration pairs, alternating configuration order. Keep errors, drops, timeouts and unknown costs. Bootstrap entire paired **session clusters**, with replacement; preserve all tasks/configurations from each sampled session. Use 95% percentile intervals. Frame count is not sample size. The configurable minimum is an operational gate, not a power calculation. Start with 30–50 real independent pilot sessions, estimate uncertainty/effect sizes, then freeze the held-out sample size. If participants contribute correlated sessions, predefine participant-level aggregation or extend the clustering protocol before claiming independence.

Engineering gates: candidate/baseline full cost ≤0.8; p95 answer latency ratio ≤0.9; mean grounded quality difference ≥0; all declared critical facts preserved. Point estimates and the relevant 95% interval bounds must satisfy gates. Held-out measured evidence and the minimum session count are also required. The plan declares `baseline`, `candidate` and `controls`; the candidate is compared separately against the baseline and each control (C/A, C/D, C/E). Deadline success remains the primary task metric; the gate's quality term is grounded correctness independent of deadline, with latency assessed separately.

Synthetic data can never pass acceptance. A numeric measured pass is `numeric_pass_requires_audit`, not a certification of data, model execution, annotation integrity or reproducibility. Quality gate margins are intentionally zero for this protocol; changing margins requires a new protocol revision.

## Continuous runtime

Run 30-minute, 2-hour and 8-hour soaks independently. Record memory slope, queue growth, reconnects, drops, stale evidence, model-server GPU memory and costs. The supplied soak command repeatedly sends recorded inline packets to one live adapter and records hash-chained outputs/resources. It is an ingestion stress harness, not evidence of correct multi-hour memory or physical sensor synchronization. Add timestamped continuous real recordings and delayed questions through a project-specific adapter/harness for those claims. Soak completion alone never grants quality acceptance.

## External benchmarks

Run each benchmark's own pinned dataset, preprocessing and scorer. Preserve its original units and publish provenance separately. A modified protocol cannot be imported as an official-protocol score. Imported records are self-reported reproductions pending review; metadata validation does not endorse them. These scores are not averaged into the Gamst score.
