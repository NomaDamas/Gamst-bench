# Gamst repository benchmark archive

## Archive source

This summary indexes the evaluation/billing implementation archived from the **Gamst** repository, not a new benchmark run. The source was Gamst branch `feat/cleanup-eval-billing` at commit `5eb94c3bf841cd50cc8fd69ab3744eeede3b73fd`. This summary is on Gamst-bench branch `docs/gamst-repo-benchmarks-archive`, based on source HEAD `f7d72f46deacecff50b459b99465d8e833619a0a`.

The full file-by-file archive covers all 65 files under Gamst `benchmarks/` (including `benchmarks/fixtures/controller-replay.json`) and all 15 removed SDK evaluation/billing modules. For every file it records purpose, inputs, metrics/specification, source references and the distinction between synthetic fixtures and measured results:

- **[Gamst benchmark and evaluation implementation archive](https://github.com/NomaDamas/Gamst/blob/feat/cleanup-eval-billing/docs/archive/benchmarks-and-evaluation.md)**
- Repository path: `NomaDamas/Gamst:docs/archive/benchmarks-and-evaluation.md`

No existing Gamst cleanup PR URL was found in the records searched for this archive, so no PR link is asserted here.

## Archived Gamst benchmark families

| Family | What the archived implementation does | Evidence status in the Gamst repository |
|---|---|---|
| Synthetic runtime and paired evaluation | `runtime.py` measures SDK ingestion/state workloads; `perception_comparison.py`, paired replay/evidence and attempt recorders define quality, critical-fact, p95, usage and exact-cost contracts. | One **actual synthetic SDK runtime** measurement is recorded in Gamst `docs/runtime-benchmark.md` (200/500 cycles, plus bounded-evidence rerun); no model-quality result and no eight-hour soak. Paired real-model acceptance remains unrecorded. |
| Three-arm and whole-stream comparison | A/B/C collection and numerical joins, native attempts, exact stream ledgers/allocation/reconciliation and matched-recording lifetime comparisons implement cost ≤0.8, p95 ≤0.9 and quality-preservation gates. | Contracts and synthetic arithmetic only; no real held-out A/B/C acceptance result is recorded for these modules. Declared hashes or complete invoices do not certify actual coverage or savings. |
| Recorded-source and persistent recording | Raw BGR/PCM replay, fixed 1× clocks/ticks, owned acquisition, Context snapshots, native4 operation journals, fixed parent/child channels and runtime/source/publication joins preserve original evidence lineage. | Synthetic files, fixture predictors and actual SDK software paths establish behavior only. No trained perception quality, sustained realtime or matched-recording efficacy result is recorded. |
| Transport and billing evidence | Direct one-attempt Responses transport, original response stores/readers, OpenAI aggregate import, native3/native4 structural indexes and offline crosschecks preserve original transport/account evidence. | Loopback HTTP and synthetic account/invoice fixtures only. No genuine OpenAI call, authenticated invoice, per-request cost or whole-pipeline monetary result is recorded. |
| Fill, sentinel and evaluation SDK hooks | Call-budget liability, native entry/publication references, frozen Context snapshots, same-capture fill conflict rules and fresh-frame Smol scheduling expose opt-in evaluation seams. | Synthetic image/model/worker fixtures verify contracts; no calibrated fill accuracy, trained Smol quality or quality-preserving cost saving is recorded. |
| ORB-SLAM replay | Pinned BGR input replay records native provider states and local unpaced request timing while leaving trajectory error and real capture latency unknown. | Test-double native bridge only; no real-device SLAM quality measurement is recorded. |

The archive deliberately treats fixture completion, structural hash integrity and software tests as **contract evidence**, not real model or financial measurements.

## Related measured evidence in Gamst-bench

These campaigns are separate from the archived Gamst modules above and must not be retroactively presented as outputs of those synthetic fixtures:

- **2026-11-16 local runtime smoke:** B/C/D/E each completed one four-frame unscored run through real local llama.cpp and pinned Qwen3-VL-2B-Instruct. This established executable paths only, not quality, resource/cost or default selection. Sources: `docs/ARMS.md`, `docs/evidence/runtime-contract-execution-2026-11-16.json`.
- **2026-11-18 GCP dev subsets:** FastBench, OmniPro and StreamArena native/extension observations are recorded with small samples and explicit protocol limitations. They are not official leaderboard submissions or superiority evidence; FastBench C/D is specifically documented as an adapter-failure/dev observation. Source: `docs/results/gcp-2026-11-18.md`.
- **2026-11-19 GAMST-HF measured baseline:** on 88 admitted StreamArena-derived episodes, `strong` scored 33/88 and `gamst` 15/88; prompt tokens were 1,067,693 and 2,006,668 respectively. The recorded interpretation is that GAMST neither matched strong-model quality nor saved tokens in this run. `gamst_nomedia` scored 8/88, and StreamingVLM native state ran on all 88 episodes with zero errors and median realtime factor 0.896. Source: `docs/results/gcp-2026-11-19-hf.md`; dataset scope and uncovered families are in `docs/GAMST_HF_DATASET.md`.

Protocol drafts for the broader semantic/high-frequency families remain distinct from those measurements: `docs/GAMST_SEMANTIC_BENCHMARK.md` and `docs/GAMST_HF_SEMANTIC_BENCHMARK.md` define transient events, episode order, AV synchronization, state/last-seen memory, revision, physical dynamics and overload/recovery, but do not themselves supply scores.
