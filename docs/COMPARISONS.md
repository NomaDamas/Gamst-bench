# Gamst hybrid comparison plan

Status: design and reference catalog ready; native benchmark adapters, actual Gamst integration and GCP model runs are pending. This document does not certify Gamst completion or superiority.

## Two evidence tracks

1. **Official replication:** retain the benchmark's released split, questions, prompts, frame policy, temporal tolerance and scorer. Record dataset, runner and model revisions. Use each benchmark's native ranking separately. Published literature is reference evidence, never our measurement. An official score upload must follow that benchmark's actual submission policy; a dashboard entry is not an official submission.
2. **Gamst system extension:** replay authorized sensor streams causally on GCP. Add complete cost, event-to-answer latency, missed evidence, false alerts, memory freshness and continuous-session stability. Give changed protocols a new name and revision. Never insert an extension score into an official ranking.

## Matched arms

- Full VLM → same memory → same consumer LLM.
- Thin perception → Gamst memory → same consumer LLM (text evidence only; no hidden semantic VLM calls).
- Gamst selection → same VLM → same memory → same consumer LLM.
- Periodic selection → same VLM → same memory → same consumer LLM.
- Small streaming VLM (E) → same memory → same consumer LLM. Its own lightweight checkpoint; tests whether Gamst beats a cheap always-on VLM.
- Native published methods under their original protocols, separately reported.

Also sweep C and D across VLM call budgets (1, 2, 3, 6, 12 per session in the fixture) on the same inputs. Headline claim format: "C reaches A's official score at N× lower whole-pipeline cost", read off this curve.

Freeze checkpoints, quantization, hardware, input availability, consumer prompt, memory capacity, output limits, budgets and dataset split before running. Run selection and memory ablations independently: identical-memory comparisons isolate selection; disabling memory tests the memory contribution. Charge thin perception, ASR, model servers, consumer inference, idle allocated GPU time and retries. Lower VLM call counts alone do not establish savings.

## Staged datasets

Phase 1: FastBench for brief events; SPOT for when to speak; OVO for past/current/future reasoning. Phase 2: StreamingBench, OmniPro and StreamArena for AV and interactive behavior. Phase 3: Inf-Streams-Eval for long sessions, OmniVideoBench for AV reasoning. VSAS-Bench remains the required official track but is blocked until its runner/data/scorer is released; Inf-Streams-Eval plus the Gamst continuous suite is a separately labelled compatibility fallback and must never be imported as a VSAS score. The source of dataset details and reference scores is `data/catalog.json`; the website reads this file and `npm run results` regenerates the README.

Acquire data on GCP only, after licenses/access are satisfied. Keep original manifests, source URLs, revisions, checksums and timestamps. Split by source video/session to prevent leakage; reserve unseen sessions for final evaluation. Keep audio/video synchronized and annotate event onset, evidence availability, valid response window, required facts, silence intervals and stale/retracted facts. Do not provide future frames or focus timestamps to the model. Human double-review a held-out subset and adjudicate disagreement.

## Readiness and acceptance

Pin Gamst and plugin commits after real provider integration and deletion/revision behavior pass. The pinned upstream evaluation document in the catalog still identifies open real-inference work. Continuous multi-query runner support and native official scorers must be validated before a complete benchmark claim; the current task-based collector and synthetic soak are insufficient for long-session claims.

First run a small GCP smoke set, then freeze the final manifest. Pair every system on the same held-out sessions; report session-cluster confidence intervals and failure denominators. Keep fixed acceptance thresholds in the frozen protocol; never tune them after seeing the test set. Report quality/cost/latency Pareto tradeoffs and unresolved uncertainty. Existing synthetic release results cannot pass real-system acceptance.

## Publication

Preserve raw traces, scorer outputs, config hashes, hardware/region, prices/date, model and dataset revisions. Import actual official results only with matching measured configuration provenance. Current literature catalog entries remain separate from `official_scores`. Update the website and README together. Submit results upstream only with required artifacts and the benchmark's requested format; do not imply organizer verification before acceptance.

See [GCP preparation](../infra/gcp/README.md). The private Aside setup has a verified GCP MCP host; this repository does not provision or publish that host's private identifiers.
